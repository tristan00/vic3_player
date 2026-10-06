insert into advisor_action (name) values ('relations')
on conflict (name) do nothing;

insert into run_weight (run_id, advisor_action, weight, centre)
select raising.run_id, fresh.advisor_action, sqrt(raising.weight * lowering.weight), (raising.centre + lowering.centre) / 2
from run_weight raising
join advisor_action positive on positive.advisor_action = raising.advisor_action and positive.name = 'raise_relations'
join run_weight lowering on lowering.run_id = raising.run_id
join advisor_action negative on negative.advisor_action = lowering.advisor_action and negative.name = 'lower_relations'
join advisor_action fresh on fresh.name = 'relations'
on conflict (run_id, advisor_action) do nothing;
