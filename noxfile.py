import nox

python_versions = ["3.9", "3.10", "3.11", "3.12", "3.13"]

@nox.session(python=python_versions)
def tests(session):
    session.install("-e", ".", "pytest")
    session.run("pytest")
