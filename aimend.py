#!/usr/bin/python

import argparse
import json
import re
import requests
import subprocess
import sys
import textwrap
import typing

from ktoolbox import host
from ktoolbox import common


logger = common.ExtendedLogger("llm-git." + __name__)

BASE_URL = "http://127.0.0.1:8080"

AIMEND_TAG = "---aimend-msg---"


def print_msg(msg: str, *, color: str = "90") -> None:
    for line in msg.splitlines():
        print(f"    \033[{color}m{line}\033[0m")


def _strip_aimend_msg(
    msg: str,
    *,
    mode: str,
    strip_aimend: bool = True,
) -> str:
    if not strip_aimend:
        pass
    elif mode == "message":
        msg = msg.strip()
        msg = re.sub(f"\n*{re.escape(AIMEND_TAG)}\n.*", "", msg, flags=re.DOTALL)
        msg = msg.strip()
    elif mode == "default":
        msg = msg.strip()
        msg = re.sub(f"\n*[\t ]*{re.escape(AIMEND_TAG)}\n.*", "", msg, flags=re.DOTALL)
        msg = msg.strip()
    elif mode == "full":
        msg = msg.strip()
        msg = re.sub(
            f"\n*[\t ]*{re.escape(AIMEND_TAG)}\n.*?\ndiff ",
            "\ndiff ",
            msg,
            flags=re.DOTALL,
        )
        msg = msg.strip()
    else:
        assert False
    return msg


def _git_revparse(commit: str) -> str:
    return host.local.run(
        ["git", "rev-parse", commit],
        die_on_error=True,
    ).out


def _git_ishead(commit: str) -> bool:
    if commit in ("HEAD", "@"):
        return True
    return _git_revparse(commit) == _git_revparse("HEAD")


def _git_prettyline(commit: str) -> str:
    return host.local.run(
        [
            "git",
            "log",
            "-n1",
            "--color=always",
            "--no-show-signature",
            "--pretty=format:%Cred%h%Creset - %Cgreen(%ci)%Creset [%C(yellow)%aN%Creset] %s%C(yellow)%d%Creset",
            "--abbrev-commit",
            "--date=local",
            commit,
        ],
        die_on_error=True,
    ).out


def _git_show(
    commit: str,
    *,
    mode: str,
) -> str:
    if mode == "full":
        args = ["git", "show", "--no-color", "--format=fuller", commit]
    elif mode == "default":
        args = ["git", "log", "-n1", "--no-color", "--format=medium", commit]
    elif mode == "message":
        args = ["git", "log", "-n1", "--pretty=%B", commit]
    else:
        assert False
    r = host.local.run(
        args,
        die_on_error=True,
    )
    return r.out


def _git_amend(msg: str) -> None:
    host.local.run(
        [
            "git",
            "commit",
            "--amend",
            "-m",
            msg,
        ],
        die_on_error=True,
    )


def _aichat_request(
    data: dict[str, typing.Any],
    token_callback: typing.Optional[typing.Callable[[str], None]] = None,
    host: str = BASE_URL,
) -> str:
    result = ""
    with requests.post(
        f"{host}/v1/chat/completions",
        headers={
            "Content-Type": "application/json",
        },
        json=data,
        stream=True,
    ) as http_response:
        for line in http_response.iter_lines(decode_unicode=True):
            if line.strip() == "" or not line.startswith("data:"):
                continue
            if line.strip() == "data: [DONE]":
                break

            # Parse and print token content
            try:
                chunk = json.loads(line.lstrip("data: "))
                delta = chunk["choices"][0].get("delta", {})
                content = delta.get("content")
                if content:
                    result += content
                    if token_callback is not None:
                        token_callback(content)
            except json.JSONDecodeError:
                continue
    return result


def _aichat_get_commitmsg(
    gcommit: str,
    *,
    show_tokens: bool = False,
    host: str = BASE_URL,
) -> str:

    data = {
        "stream": True,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a senior software engineer who writes clear and helpful git commit messages. "
                    "Use present tense. Start with a short subject line with a lowercase category tag (e.g., 'refactor:', 'style:', 'docs:', etc.), "
                    "followed by a concise lowercase summary. You may add a longer body only if it provides extra clarity."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Improve the commit message based on the following git diff. Only show the improved commit message. "
                    f"The git diff is:\n\n```\n{gcommit}\n```"
                ),
            },
        ],
    }

    logger.debug(f"request: {repr(data)}")

    response = _aichat_request(
        data,
        token_callback=(
            (lambda s: logger.debug(f"token: {repr(s)}")) if show_tokens else None
        ),
        host=host,
    )

    logger.debug(f"response: {repr(response)}")

    response = response.strip()
    response = re.sub(r"^(```)?\s*", "", response)
    response = re.sub(r"(```)?\s*$", "", response)

    logger.debug(f"response-clean: {repr(response)}")

    return response


def generate_new_msg(
    msg: str,
    *,
    old_msg: typing.Optional[str] = None,
) -> str:
    msg = "\n".join(textwrap.fill(m, width=80) for m in msg.splitlines())
    if old_msg is None:
        return f"{msg}\n"
    return f"{old_msg}\n\n{AIMEND_TAG}\n\n{msg}\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tool to improve commit message")
    parser.add_argument(
        "commit",
        nargs="?",
        help="The git commit to improve the commit message for.",
        default="HEAD",
    )
    parser.add_argument(
        "-d",
        "--diff",
        action="store_true",
        help="Whether to show also the diff to the LLM (defaults to false). This gives more context to the AI.",
    )
    parser.add_argument(
        "-a",
        "--amend",
        action="store_true",
        help="Whether to amend the commit message. This only works if the commit is HEAD.",
    )
    parser.add_argument(
        "--no-prompt",
        action="store_false",
        dest="prompt",
        default=None,
        help="When generating the HEAD, by default prompt whether to amend the commit message. Opt-out from that.",
    )
    parser.add_argument(
        "--show-tokens",
        action="store_true",
        help="Whether to log the individual tokens.",
    )
    parser.add_argument(
        "-r",
        "--replace",
        action="store_true",
        help="Whether to replace the existing commit message. Otherwise, it is appended.",
    )
    parser.add_argument(
        "--host",
        help="The local OpenAI-compatible Chat Completions API, for example, http://localhost:8080",
        default=BASE_URL,
    )

    common.log_argparse_add_argument_verbose(parser)

    args = parser.parse_args()

    common.log_config_logger(
        args.show_tokens or args.verbose,
        "llm-git",
        "ktoolbox",
    )

    args.commit_is_head = _git_ishead(args.commit)

    if args.prompt is None:
        args.prompt = not args.amend and args.commit_is_head

    if (args.amend or args.prompt) and not args.commit_is_head:
        print("The --amend/--prompt option requires the HEAD commit. See --help.")
        sys.exit(1)

    h = args.host
    if not h:
        h = BASE_URL
    else:
        if not h.startswith("http://") and not h.startswith("https://"):
            h = f"http://{h}"
    args.host = h

    return args


def main() -> None:
    args = parse_args()

    print(f"Commit: {_git_prettyline(args.commit)}")

    old_msg = _git_show(args.commit, mode="message")

    print("Old message:\n")
    print_msg(old_msg)
    print("Generate new commit message...")

    git_show_mode = "full" if args.diff else "default"

    full_msg = _git_show(args.commit, mode=git_show_mode)

    new_msg = _aichat_get_commitmsg(
        _strip_aimend_msg(full_msg, mode=git_show_mode),
        show_tokens=args.show_tokens,
        host=args.host,
    )

    new_msg = generate_new_msg(
        new_msg,
        old_msg=(None if args.replace else _strip_aimend_msg(old_msg, mode="message")),
    )

    print("New message:\n")
    print_msg(new_msg)

    if args.prompt:
        amend = input("\nAmend the commit [Y/n]: ").strip().lower() in [
            "",
            "y",
            "yes",
            "1",
        ]
    else:
        amend = args.amend

    if amend:
        _git_amend(new_msg)
        print(f"Commit: {_git_prettyline('HEAD')}")
        subprocess.run(["git", "commit", "--amend"])
        print(f"Commit: {_git_prettyline('HEAD')}")


if __name__ == "__main__":
    common.run_main(main)
