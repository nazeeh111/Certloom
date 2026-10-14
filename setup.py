"""Map source-bearing resources without moving the root development layout."""

from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py
from setuptools.command.sdist import sdist

ROOT = Path(__file__).resolve().parent
SKIP = {
    "__pycache__",
    "node_modules",
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
}


def resource_files(directory):
    source = ROOT / directory
    if source.is_symlink():
        raise ValueError("Symlink resource directory refused.")
    if not source.is_dir():
        return
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(ROOT)
        if any(part in SKIP or part.startswith("._") for part in relative.parts):
            continue
        if path.name == ".DS_Store" or path.suffix in (".pyc", ".pyo"):
            continue
        if path.is_symlink():
            raise ValueError("Symlink resource refused: " + str(relative))
        if path.is_file():
            yield path


class SourceBearingBuild(build_py):
    def run(self):
        super().run()
        for directory in ("web", "examples", "docs"):
            for source in resource_files(directory):
                destination = (
                    Path(self.build_lib) / "certloom" / source.relative_to(ROOT)
                )
                self.mkpath(str(destination.parent))
                self.copy_file(str(source), str(destination))
        destination = Path(self.build_lib) / "certloom/licenses/LICENSE"
        self.mkpath(str(destination.parent))
        self.copy_file(str(ROOT / "LICENSE"), str(destination))

    def get_outputs(self, include_bytecode=1):
        outputs = super().get_outputs(include_bytecode)
        for directory in ("web", "examples", "docs"):
            outputs.extend(
                str(Path(self.build_lib) / "certloom" / source.relative_to(ROOT))
                for source in resource_files(directory)
            )
        outputs.append(str(Path(self.build_lib) / "certloom/licenses/LICENSE"))
        return sorted(set(outputs))


class SourceBearingSdist(sdist):
    def get_file_list(self):
        super().get_file_list()
        for directory in ("web", "examples", "docs", "scripts", "tests", ".github"):
            for source in resource_files(directory):
                self.filelist.append(source.relative_to(ROOT).as_posix())
        for name in (
            "LICENSE",
            "README.md",
            "SECURITY.md",
            "pyproject.toml",
            "setup.py",
        ):
            if (ROOT / name).is_file():
                self.filelist.append(name)
        self.filelist.exclude_pattern("CONTRACT.md", anchor=False)
        self.filelist.sort()
        self.filelist.remove_duplicates()


setup(cmdclass={"build_py": SourceBearingBuild, "sdist": SourceBearingSdist})
