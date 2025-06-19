aimend
======

Tool asking a locally running LLM to generate a git commit message.

Install Dependencies:
---------------------

`pip install -r requirements.txt`


Run a LLM:
----------

run `ramalama serve mistral:latest`


Run tool:
----

```
aimend.py -h

aimend.py
```

Example:
--------

```
$ aimend.py -d -r
Commit: 0adaafa91a4f - (2025-05-23 18:14:41 +0200) [Thomas Haller] common: add as_regex() helper (HEAD -> main)
Old message:

    common: add as_regex() helper

    For out API, we want to accept either a string/bytes
    or a regex pattern. Add as_regex() helper which
    compiles a string or returns the pattern as is.

Generate new commit message...
New message:

    refactor: add as_regex helper for pattern acceptance

    Add an `as_regex` helper function that compiles a string or returns the pattern
    as is, for accepting either string/bytes or regex pattern in our API. This
    allows us to use the same API with different input types, improving code
    readability and usability. The function is overloaded to accept either a
    compiled regex pattern or a string/bytes, and returns the compiled pattern or
    None if the input is None. The DOTALL flag is used as in pexpect for finding the
    end of line.

Amend the commit [Y/n]: y
Commit: 8c35c12edc66 - (2025-06-19 19:42:54 +0200) [Thomas Haller] refactor: add as_regex helper for pattern acceptance (HEAD -> main)
```
