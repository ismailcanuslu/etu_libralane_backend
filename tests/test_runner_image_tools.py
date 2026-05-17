"""efabless/openlane imajinda web araclarinin gerektirdigi binary'leri dogrular (Docker gerekir)."""

import os
import shutil
import subprocess
import unittest

IMAGE = os.environ.get("RUNNER_IMAGE_OPENLANE", "efabless/openlane:ci2504-dev-amd64")
PLATFORM = os.environ.get("OPENLANE1_PLATFORM", "linux/amd64")

# Web katalogu: yosys + iverilog/vvp (simulation), flow icin flow.tcl proje tarafinda
REQUIRED_BINARIES = ("yosys", "iverilog", "vvp", "klayout", "magic", "openroad", "sta")


@unittest.skipUnless(shutil.which("docker"), "docker yok")
class RunnerImageToolsTests(unittest.TestCase):
  def test_required_binaries_on_path(self) -> None:
    check_script = (
      "set -e; missing=0; "
      + " ".join(
          f'command -v {name} >/dev/null 2>&1 || {{ echo MISSING:{name}; missing=1; }}; '
          for name in REQUIRED_BINARIES
      )
      + 'test "$missing" -eq 0'
    )
    result = subprocess.run(
      [
        "docker",
        "run",
        "--rm",
        "--platform",
        PLATFORM,
        IMAGE,
        "bash",
        "-lc",
        check_script,
      ],
      capture_output=True,
      text=True,
      timeout=300,
    )
    self.assertEqual(
      result.returncode,
      0,
      f"binary kontrolu basarisiz:\n{result.stdout}\n{result.stderr}",
    )


if __name__ == "__main__":
  unittest.main()
