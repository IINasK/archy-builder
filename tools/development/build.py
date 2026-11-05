"""Empacota Archy Builder com a raiz instalavel archy_builder."""
import os, zipfile, shutil

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PKG = os.path.join(RAIZ, "archy_builder")
DIST = os.path.join(RAIZ, "dist")


def main():
    os.makedirs(DIST, exist_ok=True)
    destino = os.path.join(DIST, "archy_builder.zip")
    if os.path.exists(destino):
        os.remove(destino)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        for nome in ("LICENSE", "NOTICE"):
            z.write(os.path.join(RAIZ, nome), "archy_builder/" + nome)
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
