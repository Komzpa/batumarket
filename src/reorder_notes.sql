set http.timeout_msec = 500000;
set http.keepalive = 'on';

drop table if exists sent_msgs;
create table sent_msgs (msg text);
\copy sent_msgs (msg) from 'Intermediate/sent_messages.csv' delimiter E'\b';
delete from sent_msgs where trim(msg) = '';
ALTER TABLE sent_msgs ADD COLUMN id SERIAL PRIMARY KEY;
alter table sent_msgs add column embedding vector;
update sent_msgs set embedding = openai_embeddings(msg);




drop table if exists mytasks;
create table mytasks (task text);
\copy mytasks (task) from 'Intermediate/Annotated Notes.md' delimiter E'\b';
-- \copy mytasks (task) from 'telegram_log_prefixed.txt' delimiter E'\b';
delete from mytasks where trim(task) = '';
ALTER TABLE mytasks ADD COLUMN id SERIAL PRIMARY KEY;
alter table mytasks add column embedding vector;
update mytasks set embedding = openai_embeddings(task);

drop table if exists reordered_tasks;
create table reordered_tasks as (
    with circular_tasks as (select seq, cost, node FROM pgr_TSP(
        $$
        SELECT a.id as start_vid, b.id as end_vid, a.embedding <=> b.embedding as agg_cost from mytasks a, mytasks b
        $$
    )),
    linear_tasks as (
    select  
        (seq-(select seq from circular_tasks order by cost desc limit 1) + max(seq) over()-1) % (max(seq) over()-1) as seq,
        m.id,
        m.task,
        m.embedding,
        cost
    from circular_tasks c
        join mytasks m on c.node = m.id
    where seq != 1
    order by 1),
    relevant_destinations as materialized (
        select distinct on (c.names) t.id, c.names, distance, azimuth, azimuth_emoji, similarity,
        'Distance '|| distance|| 'm azimuth ' ||azimuth::text || ' '||  azimuth_emoji||':  ' ||names as location_text
        from linear_tasks t,
        lateral (select ((c.embedding <=> t.embedding) + log(1+distance/40000.)) as similarity,  * from batumi_clusters c order by 1 limit 20) c 
        order by c.names, c.similarity
    ),
    sent_messages as materialized (
        select distinct on (m.msg) m.embedding <=> t.embedding as similarity, m.msg, t.id from sent_msgs m, mytasks t order by 2, 1
    )
    select 
        trim(task) 
        || coalesce( E'\n' || (select string_agg('Sent message: ' || trim(msg), E'\n' order by m.similarity) from sent_messages m where m.id = t.id) , '') 
        || coalesce( E'\n' || (select string_agg(trim(location_text), E'\n' order by d.similarity) from relevant_destinations d where d.id = t.id) , '') 
        as text,
--        (select string_agg('Sent message:' || trim(msg), E'\n' order by m.similarity) from sent_messages m where m.id = t.id) as sent,
        (select count(*) from sent_messages m where m.id = t.id) as sent_messages_count,
        seq 
    from linear_tasks t 
--    group by seq, task
    order by seq
);

-- drop out the things that were discussed already
delete from reordered_tasks where sent_messages_count > 2;

\copy (select text from reordered_tasks order by seq) to 'ordered_notes.txt';
