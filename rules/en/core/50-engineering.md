
## Engineering baseline

- Names express real intent; modules are cohesive; functions have a clear purpose and a consistent level of abstraction.
- Keep side effects at explicit system boundaries. Errors are observable and recoverable — never swallow them or fake success.
- Unfinished capabilities are hidden, or disabled with the reason shown, or show a real empty/failed state; never pass off mocks, delayed animations or local success flags as finished.
- Abstract only stable concepts that already repeat; don't build platforms for hypothetical future features.
- Use explicit types for states, results and errors instead of mutually exclusive booleans, magic strings or special `null`s.
- Comments explain constraints, reasons and trade-offs rather than restating code; temporary workarounds state when they can be removed.
