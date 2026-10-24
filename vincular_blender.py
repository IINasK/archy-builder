"""Liga a pasta do projeto a pasta de add-ons do Blender via junction.

Depois disso o Blender carrega o codigo direto do repositorio: editar aqui
altera o add-on, sem copiar nada. Junction no Windows nao exige admin.
"""
import os, subprocess, sys

RAIZ = os.path.dirname(os.path.abspath(__file__))
ORIGEM = os.path.join(RAIZ, "cabinet_creator")

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
        print("Nao achei instalacao do Blender em", BASE)
        return 1
    versao = sys.argv[1] if len(sys.argv) > 1 else vs[-1]
    addons = os.path.join(BASE, versao, "scripts", "addons")
    os.makedirs(addons, exist_ok=True)
    alvo = os.path.join(addons, "cabinet_creator")

    # lexists: junction QUEBRADO (repositorio mudou de lugar) tambem sai
    if os.path.lexists(alvo):
        print("Removendo o que ja estava em", alvo)
        try:
            os.rmdir(alvo)              # junction: rmdir basta
        except OSError:
            # Pasta comum (instalado por .zip) pode ter presets salvos na
            # biblioteca/: apagar sem perguntar perderia o trabalho do usuario.
            print("Ja existe uma instalacao comum em", alvo,
                  "- mova ou apague essa pasta e rode de novo.")
            return 1

    r = subprocess.run(["cmd", "/c", "mklink", "/J", alvo, ORIGEM],
                       capture_output=True)
    print(r.stdout.decode("utf-8", "replace").strip() or
          r.stderr.decode("utf-8", "replace").strip())
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
