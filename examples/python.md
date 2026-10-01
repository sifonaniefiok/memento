# Python

## What does `if __name__ == "__main__":` do?
tags: python

It runs the indented code only when the file is executed directly
(`python script.py`), not when it is imported as a module.

---

## Why is `def f(items=[])` a bug?
tags: python, gotchas

Default values are evaluated **once**, when the function is defined, so every
call shares the same list. Use `None` instead:

```python
def f(items=None):
    if items is None:
        items = []
    items.append(1)
    return items
```

---

## What is the difference between `is` and `==`?
tags: python

`==` compares **values**; `is` compares **identity** (the same object in
memory). Use `is` only for singletons such as `None`.

---

## How do you swap two variables in Python?
tags: python, idioms

```python
a, b = b, a
```

The right-hand side builds a tuple first, then unpacks it into the names on
the left.

---

## What does a list comprehension with a condition look like?
tags: python, idioms

```python
squares_of_evens = [n * n for n in range(10) if n % 2 == 0]
```
