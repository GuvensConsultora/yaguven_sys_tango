from . import models
from . import wizard


def post_init_hook(env):
    """Carga el catálogo de rubros en las compañías que ya existen."""
    env["yaguven.rubro"].cargar_catalogo()
