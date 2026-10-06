insert into advisor_action (name)
values ('military_leadership'), ('military_organisation'), ('military_operations')
on conflict (name) do nothing;

insert into run_weight (run_id, advisor_action, weight, centre)
select w.run_id, fresh.advisor_action, w.weight, w.centre
from run_weight w
join advisor_action old on old.advisor_action = w.advisor_action and old.name = 'disposition_of_forces'
cross join advisor_action fresh
where fresh.name in ('military_leadership', 'military_organisation', 'military_operations')
on conflict (run_id, advisor_action) do nothing;
