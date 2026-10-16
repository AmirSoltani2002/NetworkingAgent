from contextvars import ContextVar
from .errors import ServiceError
admin=ContextVar('zsk_admin',default=False)
def require_admin():
    if not admin.get():raise ServiceError('ADMIN_REQUIRED','Use the configured admin bearer credential for this state-changing operation',403)
