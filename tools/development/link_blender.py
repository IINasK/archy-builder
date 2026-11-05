"""Link the project folder to Blender's add-ons folder through a junction.

Blender then loads code directly from the repository: editing here
changes the add-on without copying files. Windows junctions need no admin rights."""
import os, subprocess, sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ORIGEM = os.path.join(RAIZ, "archy_builder")

APPDATA = os.environ.get("APPDATA", "")
BASE = os.path.join(APPDATA, "Blender Foundation", "Blender")


def versoes():
    if not os.path.isdir(BASE):
        return []
    return sorted(d for d in os.listdir(BASE)
                  if os.path.isdir(os.path.join(BASE, d, "scripts")))


def main():
    vs = versoes()
    if not vs:
        print("No Blender installation found in", BASE)
        return 1
    versao = sys.argv[1] if len(sys.argv) > 1 else vs[-1]
    addons = os.path.join(BASE, versao, "scripts", "addons")
    os.makedirs(addons, exist_ok=True)
    alvo = os.path.join(addons, "archy_builder")

    # lexists also finds BROKEN junctions after the repository moves.
    if os.path.lexists(alvo):
        print("Removing the existing item at", alvo)
        try:
            os.rmdir(alvo)              # Junction: rmdir is sufficient.
        except OSError:
            # A regular folder installed from ZIP may contain saved presets in
            # assets/library/: deleting it without asking would lose the user's work.
            print("A regular installation already exists at", alvo,
                  "- move or delete that folder and run again.")
            return 1

    r = subprocess.run(["cmd", "/c", "mklink", "/J", alvo, ORIGEM],
                       capture_output=True)
    print(r.stdout.decode("utf-8", "replace").strip() or
          r.stderr.decode("utf-8", "replace").strip())
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
