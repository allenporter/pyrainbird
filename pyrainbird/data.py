_DEFAULT_PAGE = 0


class Pageable(object):
    def __init__(self, page=_DEFAULT_PAGE):
        self.page = page

    def __hash__(self):
        return hash(self.page)

    def __eq__(self, o):
        return isinstance(o, Pageable) and self.page == o.page

    def __ne__(self, o):
        return not __eq__(o)

    def __str__(self):
        return "page: %d" % self.page


class Echo(object):
    def __init__(self, echo):
        self.echo = echo

    def __hash__(self):
        return hash(self.echo)

    def __eq__(self, o):
        return isinstance(o, Echo) and self.echo == o.echo

    def __ne__(self, o):
        return not __eq__(o)

    def __str__(self):
        return "echo: %02X" % self.echo


class CommandSupport(Echo):
    def __init__(self, support, echo=0):
        super(CommandSupport, self).__init__(echo)
        self.support = support

    def __eq__(self, o):
        return (
            super(CommandSupport, self).__eq__(o)
            and isinstance(o, CommandSupport)
            and o.support == self.support
        )

    def __ne__(self, o):
        return not __eq__(o)

    def __hash__(self):
        return hash((super(CommandSupport, self).__hash__(), self.support))

    def __str__(self):
        return "command support: %02X, %s" % (
            self.support,
            super(CommandSupport, self).__str__(),
        )


class ModelAndVersion(object):
    def __init__(self, model, revMajor, revMinor):
        self.model = model
        self.major = revMajor
        self.minor = revMinor

    def __hash__(self):
        return hash((self.model, self.major, self.minor))

    def __eq__(self, o):
        return (
            isinstance(o, ModelAndVersion)
            and self.model == o.model
            and self.major == o.major
            and self.minor == o.minor
        )

    def __ne__(self, o):
        return not __eq__(o)

    def __str__(self):
        return "model: %04X, version: %d.%d" % (
            self.model,
            self.major,
            self.minor,
        )


class States(object):
    def __init__(self, mask="0000"):
        self.count = len(mask) * 4
        self.mask = int(mask, 16)
        self.states = ()
        rest = mask
        while rest:
            current = int(rest[:2], 16)
            rest = rest[2:]
            for i in range(0, 8):
                self.states = self.states + (bool((1 << i) & current),)

    def active(self, number):
        return self.states[number - 1]

    def __hash__(self):
        return hash((self.count, self.mask, self.states))

    def __eq__(self, o):
        return (
            isinstance(o, States)
            and self.count == o.count
            and self.mask == o.mask
            and self.states == o.states
        )

    def __ne__(self, o):
        return not __eq__(o)

    def __str__(self):
        result = ()
        for i in range(0, self.count):
            result += ("%d:%d" % (i + 1, 1 if self.states[i] else 0),)
        return "states: %s" % ", ".join(result)


class AvailableStations(Pageable):
    def __init__(self, mask, page=_DEFAULT_PAGE):
        super(AvailableStations, self).__init__(page)
        self.stations = States(mask)

    def __hash__(self):
        return hash((super(AvailableStations, self).__hash__(), self.stations))

    def __eq__(self, o):
        return (
            super(AvailableStations, self).__eq__(o)
            and isinstance(o, AvailableStations)
            and self.stations == o.stations
        )

    def __ne__(self, o):
        return not __eq__(o)

    def __str__(self):
        return "available stations: %X, %s" % (
            self.stations.mask,
            super(AvailableStations, self).__str__(),
        )


class WaterBudget(object):
    def __init__(self, program, adjust):
        self.program = program
        self.adjust = adjust

    def __hash__(self):
        return hash((self.program, self.adjust))

    def __eq__(self, o):
        return (
            isinstance(o, WaterBudget)
            and self.program == o.program
            and self.adjust == o.adjust
        )

    def __ne__(self, o):
        return not __eq__(o)

    def __str__(self):
        return "water budget: program: %d, hi: %02X, lo: %02X" % (
            self.program,
            self.adjust,
        )
