"""Template maintenance tasks.

These tasks are to be executed with https://www.pyinvoke.org/ in Python 3.6+
and are related to the maintenance of this template project, not the child
projects generated with it.
"""
import re
import shutil
from pathlib import Path
from unittest import mock

from invoke import task
from invoke.util import yaml
from invoke.vendor.yaml3.reader import Reader

ESSENTIALS = ("git", "python3", "curl")


def _load_copier_conf():
    """Load copier.yml."""
    with open("copier.yml") as copier_fd:
        # HACK https://stackoverflow.com/a/44875714/1468388
        # TODO Remove hack when https://github.com/pyinvoke/invoke/issues/708 is fixed
        with mock.patch.object(
            Reader,
            "NON_PRINTABLE",
            re.compile(
                "[^\x09\x0A\x0D\x20-\x7E\x85\xA0-"
                "\uD7FF\uE000-\uFFFD\U00010000-\U0010FFFF]"
            ),
        ):
            return yaml.safe_load(copier_fd)


@task
def check_dependencies(c):
    """Check essential development dependencies are present."""
    failures = []
    for dependency in ESSENTIALS:
        try:
            c.run(f"{dependency} --version", hide=True)
        except Exception:
            failures.append(dependency)
    if failures:
        print(f"Missing essential dependencies: {failures}")


@task(check_dependencies)
def develop(c):
    """Set up a development environment."""
    if not (Path(c.cwd) / ".venv").is_dir():
        c.run("python3 -m venv .venv")
    c.run("git submodule update --init --checkout --recursive")
    # Ensure poetry is installed
    try:
        c.run("poetry --version")
    except Exception:
        # Official installation method of poetry
        c.run(
            "curl -sSL https://raw.githubusercontent.com/python-poetry/poetry/master/get-poetry.py | python3"
        )
    # Use poetry to set up development environment in a local venv
    c.run("poetry env use .venv/bin/python")
    c.run("poetry install")
    c.run("poetry run pre-commit install")


@task(develop)
def lint(c, verbose=False):
    """Lint & format source code."""
    flags = ["--show-diff-on-failure", "--all-files", "--color=always"]
    if verbose:
        flags.append("--verbose")
    flags = " ".join(flags)
    c.run(f"poetry run pre-commit run {flags}")


@task(develop)
def test(c, verbose=False):
    """Test project."""
    all_odoo_versions = _load_copier_conf()["odoo_version"]["choices"]
    flags = [f"-n{len(all_odoo_versions)}", "--color=yes"]
    if verbose:
        flags.append("-vv")
    flags = " ".join(flags)
    c.run(f"poetry run pytest {flags} tests")


@task(develop)
def update_test_samples(c):
    """Update default scaffolding renderings."""
    # Make sure git repo is clean
    try:
        c.run("git diff --quiet --exit-code")
    except Exception:
        print("git repo is dirty; clean it and repeat")
        raise
    all_odoo_versions = _load_copier_conf()["odoo_version"]["choices"]
    default_settings_path = Path("tests", "default_settings")
    shutil.rmtree(default_settings_path)
    default_settings_path.mkdir()
    try:
        c.run("git tag --force test")
        for odoo_version in all_odoo_versions:
            v = f"{odoo_version:.1f}"
            dst = default_settings_path / f"v{v}"
            c.run(f"poetry run copier -fr test -d odoo_version={v} copy . {dst}")
            shutil.rmtree(dst / ".git")
    finally:
        c.run("git tag --delete test")
    samples = Path("tests", "samples")
    c.run(
        "poetry run copier -fr HEAD -x '**' -x '!prod.yaml' -x '!test.yaml' "
        "-d cidr_whitelist='[123.123.123.123/24, 456.456.456.456]' "
        f"copy . {samples / 'cidr-whitelist'}",
        warn=True,
    )
    shutil.rmtree(samples / "cidr-whitelist" / ".venv")
