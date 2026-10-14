from interface.common import timed_often


class PickFirst:
    name='first'

    trained=None

    @timed_often
    def start_run(self,store,objective,kept):
        pass

    @timed_often
    def pick(self,candidates,snapshot):
        return 0,None


