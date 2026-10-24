"""Empacota o add-on em dist/cabinet_creator.zip."""
import os, zipfile, shutil

RAIZ = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(RAIZ, "cabinet_creator")
DIST = os.path.join(RAIZ, "dist")


def main():
    os.makedirs(DIST, exist_ok=True)
    destino = os.path.join(DIST, "cabinet_creator.zip")
    if os.path.exists(destino):
        os.remove(destino)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        for base, dirs, arquivos in os.walk(PKG):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for a in arquivos:
                # backups do Blender e temporarios das gravacoes atomicas
                if a.endswith((".pyc", ".pyo", ".blend1", ".blend2", ".tmp")):
                    continue
                completo = os.path.join(base, a)
                z.write(completo, os.path.relpath(completo, RAIZ))
    print("Gerado:", destino, round(os.path.getsize(destino) / 1024, 1), "KB")


if __name__ == "__main__":
    main()
