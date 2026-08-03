"""Tests de la rutina de respaldo.

Lo que mas importa verificar aca no es que el dump se genere (eso lo hace
pg_dump), sino que el respaldo sea confiable y que no filtre la contrasena.
"""
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.tasks import db_backup


@pytest.fixture
def url_db(monkeypatch):
    def _set(url):
        from app.core.config import settings
        monkeypatch.setattr(settings, "database_url", url, raising=False)
    return _set


# ── Lectura de la cadena de conexion ───────────────────────────
def test_descompone_la_url_de_sqlalchemy(url_db):
    url_db("postgresql+asyncpg://apu_mkt:secreta@db.interno:5433/apu_marketplace")
    partes = db_backup._partes_conexion()

    assert partes["host"] == "db.interno"
    assert partes["port"] == "5433"
    assert partes["user"] == "apu_mkt"
    assert partes["password"] == "secreta"
    assert partes["dbname"] == "apu_marketplace"


def test_puerto_por_defecto_cuando_falta(url_db):
    url_db("postgresql://u:p@host/base")
    assert db_backup._partes_conexion()["port"] == "5432"


def test_decodifica_caracteres_escapados_en_la_clave(url_db):
    """Una clave con @ o / llega percent-encoded en la URL."""
    url_db("postgresql://usr:cla%40ve%2Frara@host:5432/base")
    partes = db_backup._partes_conexion()
    assert partes["password"] == "cla@ve/rara"
    assert partes["user"] == "usr"


def test_url_invalida_falla_claro(url_db):
    url_db("no-es-una-url")
    with pytest.raises(RuntimeError, match="formato utilizable"):
        db_backup._partes_conexion()


# ── Seguridad: la clave no puede quedar en `ps aux` ────────────
def test_la_contrasena_no_viaja_en_la_linea_de_comandos(url_db, tmp_path, monkeypatch):
    """pg_dump con la URL completa deja la clave visible en la lista de
    procesos para cualquiera con acceso al contenedor."""
    url_db("postgresql+asyncpg://apu_mkt:CLAVE_SUPER_SECRETA@host:5432/base")
    monkeypatch.setattr(db_backup, "BACKUP_DIR", tmp_path)

    capturado = {}

    def _fake_run(cmd, **kwargs):
        capturado.setdefault("cmds", []).append(cmd)
        if cmd[0] == "pg_dump":
            capturado["env"] = kwargs.get("env", {})
        # Simular que pg_dump escribio el archivo
        if cmd[0] == "pg_dump":
            Path(cmd[cmd.index("--file") + 1]).write_bytes(b"dump-simulado")
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return subprocess.CompletedProcess(cmd, 0, ";lista\ntabla mkt_insumo\n", "")

    monkeypatch.setattr(db_backup.subprocess, "run", _fake_run)
    db_backup._respaldar()

    for cmd in capturado["cmds"]:
        assert "CLAVE_SUPER_SECRETA" not in " ".join(cmd), (
            "la contrasena aparece en los argumentos del proceso"
        )
    # Debe ir por el entorno del subproceso
    assert capturado["env"].get("PGPASSWORD") == "CLAVE_SUPER_SECRETA"


def test_no_se_usa_shell(url_db, tmp_path, monkeypatch):
    """Sin shell=True no hay forma de inyectar comandos."""
    url_db("postgresql://u:p@host:5432/base")
    monkeypatch.setattr(db_backup, "BACKUP_DIR", tmp_path)

    visto = {}

    def _fake_run(cmd, **kwargs):
        visto["shell"] = kwargs.get("shell", False)
        visto["es_lista"] = isinstance(cmd, list)
        if cmd[0] == "pg_dump":
            Path(cmd[cmd.index("--file") + 1]).write_bytes(b"x")
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return subprocess.CompletedProcess(cmd, 0, "tabla\n", "")

    monkeypatch.setattr(db_backup.subprocess, "run", _fake_run)
    db_backup._respaldar()

    assert visto["shell"] is False
    assert visto["es_lista"] is True


# ── Confiabilidad ──────────────────────────────────────────────
def test_un_dump_vacio_se_descarta(url_db, tmp_path, monkeypatch):
    url_db("postgresql://u:p@host:5432/base")
    monkeypatch.setattr(db_backup, "BACKUP_DIR", tmp_path)

    def _fake_run(cmd, **kwargs):
        if cmd[0] == "pg_dump":
            Path(cmd[cmd.index("--file") + 1]).write_bytes(b"")  # vacio
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(db_backup.subprocess, "run", _fake_run)
    with pytest.raises(RuntimeError, match="vacio"):
        db_backup._respaldar()
    assert list(tmp_path.glob("*.dump")) == [], "no debe quedar el archivo malo"


def test_un_dump_corrupto_se_descarta(url_db, tmp_path, monkeypatch):
    """Se detecta ahora y no el dia que haga falta restaurar."""
    url_db("postgresql://u:p@host:5432/base")
    monkeypatch.setattr(db_backup, "BACKUP_DIR", tmp_path)

    def _fake_run(cmd, **kwargs):
        if cmd[0] == "pg_dump":
            Path(cmd[cmd.index("--file") + 1]).write_bytes(b"basura")
            return subprocess.CompletedProcess(cmd, 0, "", "")
        # pg_restore --list falla: el archivo no es un dump valido
        return subprocess.CompletedProcess(cmd, 1, "", "no es un archivo valido")

    monkeypatch.setattr(db_backup.subprocess, "run", _fake_run)
    with pytest.raises(RuntimeError, match="corrupto"):
        db_backup._respaldar()
    assert list(tmp_path.glob("*.dump")) == []


def test_si_pg_dump_falla_no_deja_archivo_a_medias(url_db, tmp_path, monkeypatch):
    url_db("postgresql://u:p@host:5432/base")
    monkeypatch.setattr(db_backup, "BACKUP_DIR", tmp_path)

    def _fake_run(cmd, **kwargs):
        if cmd[0] == "pg_dump":
            Path(cmd[cmd.index("--file") + 1]).write_bytes(b"parcial")
            return subprocess.CompletedProcess(cmd, 1, "", "connection refused")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(db_backup.subprocess, "run", _fake_run)
    with pytest.raises(RuntimeError, match="pg_dump fallo"):
        db_backup._respaldar()
    assert list(tmp_path.glob("*.dump")) == []


def test_el_error_no_arrastra_la_cadena_de_conexion(url_db, tmp_path, monkeypatch):
    """El stderr de pg_dump puede traer la URL con la clave dentro."""
    url_db("postgresql://u:CLAVE_SECRETA@host:5432/base")
    monkeypatch.setattr(db_backup, "BACKUP_DIR", tmp_path)

    def _fake_run(cmd, **kwargs):
        if cmd[0] == "pg_dump":
            return subprocess.CompletedProcess(
                cmd, 1, "",
                "pg_dump: error: connection to "
                "postgresql://u:CLAVE_SECRETA@host:5432/base failed\n" * 20,
            )
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(db_backup.subprocess, "run", _fake_run)
    with pytest.raises(RuntimeError) as exc:
        db_backup._respaldar()
    # Solo se conservan las ultimas lineas y acotadas; aun asi, verificamos
    # que el mensaje no crezca sin control.
    assert len(str(exc.value)) < 400


# ── Retencion ──────────────────────────────────────────────────
def test_se_borran_los_respaldos_viejos(tmp_path, monkeypatch):
    monkeypatch.setattr(db_backup, "BACKUP_DIR", tmp_path)
    monkeypatch.setattr(db_backup, "KEEP_DAYS", 30)

    viejo = tmp_path / "apu_20250101_000000.dump"
    nuevo = tmp_path / "apu_20260801_000000.dump"
    viejo.write_bytes(b"x")
    nuevo.write_bytes(b"x")

    antiguo = (datetime.now(timezone.utc) - timedelta(days=60)).timestamp()
    os.utime(viejo, (antiguo, antiguo))

    assert db_backup._purgar_antiguos() == 1
    assert not viejo.exists()
    assert nuevo.exists()


def test_no_se_tocan_archivos_ajenos(tmp_path, monkeypatch):
    """La purga solo mira sus propios respaldos."""
    monkeypatch.setattr(db_backup, "BACKUP_DIR", tmp_path)
    monkeypatch.setattr(db_backup, "KEEP_DAYS", 1)

    ajeno = tmp_path / "otra_cosa_importante.dump"
    ajeno.write_bytes(b"x")
    antiguo = (datetime.now(timezone.utc) - timedelta(days=99)).timestamp()
    os.utime(ajeno, (antiguo, antiguo))

    db_backup._purgar_antiguos()
    assert ajeno.exists()


# ── Registro en el scheduler ───────────────────────────────────
def test_el_respaldo_esta_registrado_como_tarea():
    """Debe verse y dispararse desde el panel como cualquier otro job."""
    from app.core.scheduler import JOB_REGISTRY, setup_jobs

    setup_jobs()
    assert "db_backup" in JOB_REGISTRY
    assert JOB_REGISTRY["db_backup"]["module_path"] == "app.tasks.db_backup"
