_DEFAULT_PAGE = 0


class Pageable(object):
    def __init__(self, page=_DEFAULT_PAGE):
        self.page = page


class Echo(object):
    def __init__(self, echo):
        self.echo = echo


class CommandSupport(Echo):
    def __init__(self, support, echo=0):
        super().__init__(echo)
        self.support = support


class ModelAndVersion(object):
    def __init__(self, model, revMajor, revMinor):
        self.model = model
        self.major = revMajor
        self.minor = revMinor


class States(object):
    def __init__(self, mask: str):
        self.count = len(mask) * 4
        self.mask = int(mask, 16)
        self.states = ()
        for i in range(1, self.count):
            self.states = self.states + (bool((1 << (i - 1)) and self.mask),)

    def active(self, number):
        return self.states[number]


class AvailableStations(Pageable):
    def __init__(self, mask: str, page=_DEFAULT_PAGE):
        super().__init__(page)
        self.stations = States(mask)


class WaterBudget(object):
    def __init__(self, program, high_byte, low_byte):
        self.program = program
        self.low_byte = low_byte
        self.high_byte = high_byte
