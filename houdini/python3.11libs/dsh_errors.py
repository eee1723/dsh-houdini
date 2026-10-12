"""Houdini errors. Executed on the Bridge owning thread."""
from __future__ import annotations




class CheckpointError(RuntimeError):
    """A failed operation retains machine-readable evidence in the Bridge ledger."""
    def __init__(self, message, evidence):
        super().__init__(message)
        self.evidence = evidence


class PreflightError(ValueError):
    """Independent static errors collected before module creation starts."""
    def __init__(self, errors):
        self.evidence = {'ok': False, 'phase': 'static_preflight', 'scene_writes': 0,
                         'errors': errors[:32], 'error_count': len(errors),
                         'errors_truncated': len(errors) > 32,
                         'next_action': 'Fix the listed fields together; no nodes were created by this module.'}
        super().__init__('module static preflight failed (zero scene writes): ' +
                         '; '.join(f"{e['node']}: {e['message']}" for e in errors[:32]))


class ParameterPatchError(ValueError):
    """Literal patch validation failed before any parameter in the batch changed."""
    def __init__(self, message, parameter):
        super().__init__(message)
        self.evidence = {'ok': False, 'phase': 'parameter_patch_preflight', 'scene_writes': 0,
                         'parameter': parameter, 'next_action': 'Read the current raw string and source_sha256 with read_parms; fix all patch anchors before retrying.'}
