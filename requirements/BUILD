import os

def requirement_lines(filename):
    with open(filename) as requirements_file:
        for requirement_line in requirements_file:
            requirements_line = requirement_line.strip()
            if requirements_line[0] in ("#", "-"):
                continue
            yield requirements_line


def build_requirements(requirements_path):
    requirements = []
    for requirement_line in requirement_lines(requirements_path):
        req = python_requirement(requirement_line)
        requirements.append(
            "requirements:" + req.project_name
        )
    return requirements


def build_target(requirements_name):
    requirements_file = requirements_name + ".txt"
    python_requirements(requirements_relpath=requirements_file)
    requirements_path = buildfile_path() + "/" + requirements_file
    target(
        name=requirements_name,
        dependencies=build_requirements(requirements_path)
    )

build_target("flocker")
