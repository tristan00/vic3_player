import ast
import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FOLDERS=('interface','loop','advisors','dashboard/server')
EXEMPT=json.loads((Path(__file__).parent/'timing_exempt.json').read_text(encoding='utf-8'))
REASONS={'hot','loop','timer','monitor','declaration','tool'}
TIMERS={'timed','timed_often'}
ROUTES={'get','post','put','delete','middleware','exception_handler'}


def name_of(decorator):
    if isinstance(decorator,ast.Call):
        decorator=decorator.func
    return decorator.attr if isinstance(decorator,ast.Attribute) else decorator.id if isinstance(decorator,ast.Name) else None


def functions(tree):
    found=[]

    def walk(node,prefix,nested):
        for child in ast.iter_child_nodes(node):
            if isinstance(child,(ast.FunctionDef,ast.AsyncFunctionDef)):
                found.append((prefix+child.name,child,nested))
                walk(child,prefix+child.name+'.',True)
            elif isinstance(child,ast.ClassDef):
                walk(child,prefix+child.name+'.',nested)
            else:
                walk(child,prefix,nested)
    walk(tree,'',False)
    return found


def own_nodes(function):
    pending=list(ast.iter_child_nodes(function))
    while pending:
        node=pending.pop()
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.Lambda)):
            continue
        yield node
        pending+=ast.iter_child_nodes(node)


def covered_elsewhere(name,node,nested):
    decorators={name_of(decorator) for decorator in node.decorator_list}
    last=name.rsplit('.',1)[-1]
    return (nested or isinstance(node,ast.AsyncFunctionDef) or decorators&ROUTES or (last.startswith('__') and last!='__init__')
            or any(isinstance(inner,(ast.Yield,ast.YieldFrom)) for inner in own_nodes(node)))


def survey():
    timed,untimed=set(),set()
    for folder in FOLDERS:
        for path in sorted((ROOT/folder).rglob('*.py')):
            file=path.relative_to(ROOT).as_posix()
            for name,node,nested in functions(ast.parse(path.read_text(encoding='utf-8'))):
                if covered_elsewhere(name,node,nested):
                    continue
                decorators={name_of(decorator) for decorator in node.decorator_list}
                (timed if decorators&TIMERS else untimed).add((file,name))
    return timed,untimed


def exempt():
    whole={file for file,why in EXEMPT.items() if isinstance(why,str)}
    named={(file,name) for file,names in EXEMPT.items() if isinstance(names,dict) for name in names}
    return whole,named


class TimingCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.timed,cls.untimed=survey()
        cls.whole,cls.named=exempt()

    def test_every_function_is_timed_or_listed_with_a_reason(self):
        missing=sorted((file,name) for file,name in self.untimed if file not in self.whole and (file,name) not in self.named)
        self.assertEqual(missing,[],'add @timed or @timed_often, or list the function in tests/timing_exempt.json with its reason')

    def test_every_listed_exemption_names_an_untimed_function(self):
        stale=sorted(self.named-self.untimed)
        self.assertEqual(stale,[],'these exemptions name a function that is timed or no longer exists')
        files={file for file,_ in self.timed|self.untimed}
        self.assertEqual(sorted(self.whole-files),[])

    def test_every_exemption_gives_a_known_reason(self):
        reasons={why for why in EXEMPT.values() if isinstance(why,str)}|{why for names in EXEMPT.values() if isinstance(names,dict) for why in names.values()}
        self.assertLessEqual(reasons,REASONS)

    def test_most_functions_are_timed(self):
        self.assertGreater(len(self.timed),8*len(self.named))


if __name__=='__main__':
    unittest.main()
