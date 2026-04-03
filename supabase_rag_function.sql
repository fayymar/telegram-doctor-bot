create or replace function match_medical_embeddings(
  query_embedding vector(384),
  match_threshold float,
  match_count int
)
returns table (
  id int,
  code text,
  disease_name text,
  symptoms text,
  specialist text,
  similarity float
)
language sql stable
as $$
  select
    id,
    code,
    disease_name,
    symptoms,
    specialist,
    1 - (embedding <=> query_embedding) as similarity
  from medical_embeddings
  where 1 - (embedding <=> query_embedding) > match_threshold
  order by embedding <=> query_embedding
  limit match_count;
$$;
