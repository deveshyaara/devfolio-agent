-- Run as Supabase database owner. No browser API schema is exposed.
BEGIN;
CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;
CREATE SCHEMA IF NOT EXISTS devfolio;
REVOKE ALL ON SCHEMA devfolio FROM PUBLIC, anon, authenticated;

DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'devfolio_reader') THEN
    CREATE ROLE devfolio_reader NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'devfolio_writer') THEN
    CREATE ROLE devfolio_writer NOLOGIN;
  END IF;
END $$;

CREATE TABLE devfolio.indexes (
  id text PRIMARY KEY,
  profile jsonb NOT NULL,
  dimensions integer NOT NULL CHECK (dimensions IN (768,1536,3072)),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (id, dimensions)
);
CREATE TABLE devfolio.scopes (
  id text PRIMARY KEY,
  active_index text REFERENCES devfolio.indexes(id),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE devfolio.repositories (
  scope text NOT NULL REFERENCES devfolio.scopes(id),
  index_id text NOT NULL REFERENCES devfolio.indexes(id),
  github_id bigint NOT NULL,
  name text NOT NULL,
  url text NOT NULL,
  metadata jsonb NOT NULL,
  revision text NOT NULL,
  synced_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (scope,index_id,github_id)
);
CREATE TABLE devfolio.files (
  scope text NOT NULL,
  index_id text NOT NULL,
  github_id bigint NOT NULL,
  path text NOT NULL,
  blob_sha text NOT NULL,
  content_hash text NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (scope,index_id,github_id,path),
  FOREIGN KEY (scope,index_id,github_id) REFERENCES devfolio.repositories ON DELETE CASCADE
);
-- Cache is durable before snapshot replacement, so failed publication can reuse vectors.
CREATE TABLE devfolio.embeddings (
  index_id text NOT NULL,
  content_hash text NOT NULL,
  dimensions integer NOT NULL,
  embedding extensions.vector NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (index_id,content_hash),
  FOREIGN KEY (index_id,dimensions) REFERENCES devfolio.indexes(id,dimensions),
  CHECK (extensions.vector_dims(embedding) = dimensions),
  CHECK (extensions.vector_norm(embedding) > 0)
);
CREATE TABLE devfolio.chunks (
  scope text NOT NULL,
  index_id text NOT NULL,
  github_id bigint NOT NULL,
  path text NOT NULL,
  id text NOT NULL,
  chunk_index integer NOT NULL CHECK (chunk_index >= 0),
  content text NOT NULL CHECK (length(content) <= 2400),
  content_hash text NOT NULL,
  commit_sha text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (scope,index_id,github_id,id),
  UNIQUE (scope,index_id,github_id,path,chunk_index),
  FOREIGN KEY (scope,index_id,github_id,path) REFERENCES devfolio.files ON DELETE CASCADE,
  FOREIGN KEY (index_id,content_hash) REFERENCES devfolio.embeddings
);
CREATE TABLE devfolio.sync_runs (
  id uuid PRIMARY KEY,
  scope text NOT NULL REFERENCES devfolio.scopes(id),
  index_id text NOT NULL REFERENCES devfolio.indexes(id),
  started_at timestamptz NOT NULL DEFAULT now(),
  ended_at timestamptz,
  status text NOT NULL CHECK (status IN ('running','success','failed')),
  report jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX chunks_file ON devfolio.chunks(scope,index_id,github_id,path);
CREATE INDEX runs_started ON devfolio.sync_runs(started_at DESC);
-- Exact cosine search is intentional for a small portfolio. Benchmark before HNSW.
CREATE FUNCTION devfolio.match_chunks(
  query_embedding extensions.vector, expected_index text, target_scope text,
  result_limit integer DEFAULT 4, min_score double precision DEFAULT 0.5,
  repo_name text DEFAULT NULL
) RETURNS TABLE(content text, metadata jsonb, score double precision)
LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path = '' AS $$
DECLARE expected_dimensions integer;
BEGIN
  SELECT i.dimensions INTO expected_dimensions
    FROM devfolio.indexes i JOIN devfolio.scopes s ON s.active_index=i.id
    WHERE s.id=target_scope AND i.id=expected_index;
  IF expected_dimensions IS NULL THEN
    RAISE EXCEPTION 'Index unavailable or profile mismatch';
  END IF;
  IF extensions.vector_dims(query_embedding) <> expected_dimensions THEN
    RAISE EXCEPTION 'Query dimensions do not match index';
  END IF;
  RETURN QUERY
  SELECT c.content,
    jsonb_build_object('name',r.name,'url',r.url,'path',c.path,'chunk_id',c.id,
      'chunk_index',c.chunk_index,'content_hash',c.content_hash,'commit_sha',c.commit_sha,
      'model',i.profile->>'model','model_version',i.profile->>'version'),
    1 - (e.embedding OPERATOR(extensions.<=>) query_embedding)
  FROM devfolio.chunks c
  JOIN devfolio.repositories r USING(scope,index_id,github_id)
  JOIN devfolio.embeddings e USING(index_id,content_hash)
  JOIN devfolio.indexes i ON i.id=c.index_id
  WHERE c.scope=target_scope AND c.index_id=expected_index
    AND (repo_name IS NULL OR r.name=repo_name)
    AND 1 - (e.embedding OPERATOR(extensions.<=>) query_embedding) >= min_score
  ORDER BY e.embedding OPERATOR(extensions.<=>) query_embedding, c.id
  LIMIT greatest(1,least(result_limit,40));
END $$;
REVOKE ALL ON FUNCTION devfolio.match_chunks FROM PUBLIC, anon, authenticated;

DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY['indexes','scopes','repositories','files','embeddings','chunks','sync_runs'] LOOP
    EXECUTE format('ALTER TABLE devfolio.%I ENABLE ROW LEVEL SECURITY',t);
    EXECUTE format('REVOKE ALL ON devfolio.%I FROM PUBLIC, anon, authenticated',t);
    EXECUTE format('CREATE POLICY writer_all ON devfolio.%I TO devfolio_writer USING (true) WITH CHECK (true)',t);
  END LOOP;
  FOREACH t IN ARRAY ARRAY['indexes','scopes','repositories','chunks','embeddings'] LOOP
    EXECUTE format('CREATE POLICY reader_select ON devfolio.%I FOR SELECT TO devfolio_reader USING (true)',t);
    EXECUTE format('GRANT SELECT ON devfolio.%I TO devfolio_reader',t);
  END LOOP;
END $$;
GRANT USAGE ON SCHEMA devfolio,extensions TO devfolio_reader,devfolio_writer;
GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA devfolio TO devfolio_writer;
GRANT EXECUTE ON FUNCTION devfolio.match_chunks TO devfolio_reader,devfolio_writer;
COMMIT;
