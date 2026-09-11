Planted defect: README.md asserts round_price supports a mode parameter for ceil and floor, but the code does not implement it.
Why it is objective: The signature and implementation in src/price_calc.py accept only amount and step, lacking any mode parameter.
What a reviewer must read: Compare the README.md documentation addition with the round_price signature and body in src/price_calc.py.
