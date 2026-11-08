"""
Утилита для резервных копий (запускается на своём компьютере, не на сервере).

  python scripts/backup_tool.py keygen <файл_закрытого_ключа>
      Создаёт пару ключей. Закрытый ключ пишется в файл (храните его надёжно,
      например в менеджере паролей: без него копии не расшифровать).
      Открытый ключ печатается — его кладут в BACKUP_PUBLIC_KEY на сервере.

  python scripts/backup_tool.py decrypt <копия.json.gz.enc> <файл_закрытого_ключа> [выход.json]
      Расшифровывает скачанную из R2 копию в JSON.
"""
import gzip
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.backup_crypto import decrypt, generate_keypair  # noqa: E402


def keygen(private_path: str) -> None:
    path = Path(private_path)
    if path.exists():
        sys.exit(f"{path} уже существует — не перезаписываю")
    private, public = generate_keypair()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(private + "\n")
    print(f"Закрытый ключ записан в {path}")
    print(f"BACKUP_PUBLIC_KEY={public}")


def decrypt_file(blob_path: str, private_path: str, out_path: str | None) -> None:
    private = Path(private_path).read_text().strip()
    data = gzip.decompress(decrypt(Path(blob_path).read_bytes(), private))
    if out_path:
        # Медицинские данные: файл только для владельца, существующий не трогаем
        try:
            fd = os.open(out_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            sys.exit(f"{out_path} уже существует — не перезаписываю")
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        print(f"Готово: {out_path}")
    else:
        sys.stdout.write(data.decode())


def main(argv: list[str]) -> None:
    if len(argv) == 2 and argv[0] == "keygen":
        keygen(argv[1])
    elif len(argv) in (3, 4) and argv[0] == "decrypt":
        decrypt_file(argv[1], argv[2], argv[3] if len(argv) == 4 else None)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
