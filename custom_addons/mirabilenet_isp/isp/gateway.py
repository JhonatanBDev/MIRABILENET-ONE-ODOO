"""Puerta única hacia los routers.

Los modelos nunca hablan con RouterOS directamente: piden las operaciones aquí.
RealRouterGateway usa el cliente de la API de RouterOS; FakeRouterGateway es un
doble en memoria para desarrollo y pruebas.

PENDIENTE DE LABORATORIO: el cliente de RouterOS no se probó contra equipos
reales. Todo cambio en routeros.py o en RealRouterGateway se valida en
laboratorio antes de usarlo en producción.
"""
import subprocess
import sys

from .routeros import RouterOSClient, RouterOSError

ACTIONS = ("activar", "suspender", "corte_parcial", "cambiar_plan", "desconectar", "baja")


class GatewayError(Exception):
    """El equipo no pudo aplicar o confirmar la orden."""


class RouterTarget:
    """Lo que hace falta para llegar a un router."""

    def __init__(self, name, host, user, password, port=8728):
        self.name, self.host, self.user, self.password, self.port = (
            name, host, user, password, port)


class RouterGateway:
    def apply(self, target, action, username, profile=None, reduced_profile=None):
        """Aplica la acción sobre la cuenta PPPoE y devuelve
        {"summary", "enabled", "profile", "synced"}. Lanza GatewayError si falla."""
        raise NotImplementedError

    def identify(self, target):
        """{"identity", "version"} del equipo."""
        raise NotImplementedError

    def ping(self, host):
        raise NotImplementedError


class RealRouterGateway(RouterGateway):

    def _client(self, target):
        return RouterOSClient(host=target.host, usuario=target.user,
                              contrasena=target.password, puerto=target.port)

    def apply(self, target, action, username, profile=None, reduced_profile=None):
        try:
            with self._client(target) as api:
                secret = api.buscar_secret(username)
                if secret is None:
                    raise GatewayError(
                        "El secreto %s no existe en %s." % (username, target.name))
                secret_id = secret.get(".id", "")
                enabled = secret.get("disabled", "false") not in ("true", "yes")
                applied = secret.get("profile", "")
                if action in ("suspender", "baja"):
                    api.habilitar_secret(secret_id, False)
                    api.desconectar_sesion(username)
                    enabled = False
                    summary = "Secreto %s deshabilitado y sesión cerrada." % username
                elif action == "corte_parcial":
                    applied = reduced_profile or profile
                    api.actualizar_secret(secret_id, profile=applied)
                    api.desconectar_sesion(username)
                    summary = "Secreto %s movido al perfil reducido %s." % (username, applied)
                elif action == "activar":
                    applied = profile
                    api.actualizar_secret(secret_id, profile=applied)
                    api.habilitar_secret(secret_id, True)
                    enabled = True
                    summary = "Secreto %s habilitado en %s." % (username, applied)
                elif action == "cambiar_plan":
                    applied = profile
                    api.actualizar_secret(secret_id, profile=applied)
                    summary = "Secreto %s cambiado a %s." % (username, applied)
                elif action == "desconectar":
                    api.desconectar_sesion(username)
                    summary = "Sesión de %s desconectada." % username
                else:
                    raise GatewayError("Acción desconocida: %s" % action)
                # Se relee el secreto: sin confirmación no hay cambio de estado.
                synced = api.buscar_secret(username) is not None
        except (RouterOSError, OSError) as exc:
            raise GatewayError(str(exc))
        return {"summary": summary, "enabled": enabled, "profile": applied, "synced": synced}

    def identify(self, target):
        try:
            with self._client(target) as api:
                return {"identity": api.identidad(), "version": api.version()}
        except (RouterOSError, OSError) as exc:
            raise GatewayError(str(exc))

    def ping(self, host, attempts=2, timeout=2):
        if sys.platform.startswith("win"):
            command = ["ping", "-n", str(attempts), "-w", str(timeout * 1000), host]
        else:
            command = ["ping", "-c", str(attempts), "-W", str(timeout), host]
        try:
            result = subprocess.run(command, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL,
                                    timeout=timeout * attempts + 2)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            return False


class FakeRouterGateway(RouterGateway):
    """Routers en memoria. `secrets[host][usuario] = {"enabled", "profile"}`."""

    secrets = {}
    identities = {}
    unreachable = set()
    failures = []
    calls = []

    @classmethod
    def reset(cls):
        cls.secrets, cls.identities = {}, {}
        cls.unreachable, cls.failures, cls.calls = set(), [], []

    @classmethod
    def add_secret(cls, host, username, profile="default", enabled=False):
        cls.secrets.setdefault(host, {})[username] = {"enabled": enabled, "profile": profile}

    def _check(self, target):
        if type(self).failures:
            raise GatewayError(type(self).failures.pop(0))
        if target.host in type(self).unreachable:
            raise GatewayError("Sin respuesta de %s." % target.name)
        if not target.password:
            raise GatewayError("Credenciales rechazadas por el router.")

    def apply(self, target, action, username, profile=None, reduced_profile=None):
        type(self).calls.append((target.host, action, username))
        self._check(target)
        secret = type(self).secrets.get(target.host, {}).get(username)
        if secret is None:
            raise GatewayError("El secreto %s no existe en %s." % (username, target.name))
        if action in ("suspender", "baja"):
            secret["enabled"] = False
            summary = "Secreto %s deshabilitado y sesión cerrada." % username
        elif action == "corte_parcial":
            secret["profile"] = reduced_profile or profile
            summary = "Secreto %s movido al perfil reducido %s." % (username, secret["profile"])
        elif action == "activar":
            secret.update(enabled=True, profile=profile)
            summary = "Secreto %s habilitado en %s." % (username, profile)
        elif action == "cambiar_plan":
            secret["profile"] = profile
            summary = "Secreto %s cambiado a %s." % (username, profile)
        elif action == "desconectar":
            summary = "Sesión de %s desconectada." % username
        else:
            raise GatewayError("Acción desconocida: %s" % action)
        return {"summary": summary, "enabled": secret["enabled"],
                "profile": secret["profile"], "synced": True}

    def identify(self, target):
        self._check(target)
        return dict(type(self).identities.get(target.host, {"identity": "", "version": ""}))

    def ping(self, host):
        return host not in type(self).unreachable
