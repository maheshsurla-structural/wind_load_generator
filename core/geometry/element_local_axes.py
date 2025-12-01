# core/geometry/element_local_axes.py

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Tuple

import numpy as np


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LocalAxes:
    """
    Element local axes in GLOBAL coordinates.

    ex, ey, ez are 3-component numpy arrays (unit vectors) such that:

        - ex  : local x-axis (N1 -> N2)
        - ey  : local y-axis
        - ez  : local z-axis
        - [ex ey ez] is right-handed and orthonormal

    All vectors are expressed in the GLOBAL coordinate system.
    """
    ex: np.ndarray
    ey: np.ndarray
    ez: np.ndarray

    @property
    def T_gl_to_loc(self) -> np.ndarray:
        """
        3x3 transformation matrix: GLOBAL -> LOCAL.
        For a global vector v_g, v_loc = T_gl_to_loc @ v_g.
        """
        # rows are local basis in global components
        ex, ey, ez = self.ex, self.ey, self.ez
        return np.vstack([ex, ey, ez])

    @property
    def T_loc_to_gl(self) -> np.ndarray:
        """
        3x3 transformation matrix: LOCAL -> GLOBAL.
        For a local vector v_loc, v_g = T_loc_to_gl @ v_loc.
        """
        # columns are local basis in global components
        ex, ey, ez = self.ex, self.ey, self.ez
        return np.column_stack([ex, ey, ez])


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------

EX = np.array([1.0, 0.0, 0.0])  # global X
EY = np.array([0.0, 1.0, 0.0])  # global Y (not directly used, but handy)
EZ = np.array([0.0, 0.0, 1.0])  # global Z


def compute_element_local_axes(
    n1: Tuple[float, float, float],
    n2: Tuple[float, float, float],
    beta_deg: float,
    *,
    tol: float = 1e-8,
) -> LocalAxes:
    """
    Compute element local axes following MIDAS convention.

    Parameters
    ----------
    n1, n2 : (x, y, z) coordinates of the element end nodes in GLOBAL system.
             Local x is always from n1 -> n2.
    beta_deg : Beta angle from MIDAS (degrees).
        - If local x is parallel to global Z:
            beta is the angle from global X to local z, about local x.
        - Otherwise:
            beta is about local x, starting from a reference z0 which is the
            projection of global Z onto the plane normal to local x.
    tol : tolerance used to decide if the member is "vertical".

    Returns
    -------
    LocalAxes
        ex, ey, ez as unit vectors in GLOBAL coordinates, plus
        convenience transformation matrices via properties.
    """
    r1 = np.asarray(n1, dtype=float)
    r2 = np.asarray(n2, dtype=float)

    # ------------------------------------------------------------------
    # 1) Local x-axis (N1 -> N2)
    # ------------------------------------------------------------------
    x_vec = r2 - r1
    norm_x = np.linalg.norm(x_vec)
    if norm_x < tol:
        raise ValueError("N1 and N2 are coincident; cannot define local axes.")

    ex = x_vec / norm_x

    # ------------------------------------------------------------------
    # 2) Decide if element is "vertical" (local x ∥ global Z)
    # ------------------------------------------------------------------
    cos_theta = float(np.dot(ex, EZ))  # cos(angle between ex and global Z)
    is_vertical = abs(abs(cos_theta) - 1.0) < tol

    beta_rad = math.radians(beta_deg)

    # ------------------------------------------------------------------
    # 3) Reference z0 before applying beta
    # ------------------------------------------------------------------
    if is_vertical:
        # Vertical member: reference z is global X (orthogonal to Z)
        z0 = EX.copy()
        # For safety, if ex is accidentally close to EX, switch to global Y
        if abs(np.dot(z0, ex)) > 1.0 - tol:
            z0 = EY.copy()
    else:
        # Non-vertical member: z0 is projection of global Z onto plane ⟂ ex
        proj = EZ - np.dot(EZ, ex) * ex
        norm_proj = np.linalg.norm(proj)
        if norm_proj < tol:
            # Numerically fell back to "vertical"
            z0 = EX.copy()
        else:
            z0 = proj / norm_proj

    # ------------------------------------------------------------------
    # 4) Rotate z0 around ex by beta to get final ez
    # ------------------------------------------------------------------
    ez = _rotate_around_axis(z0, ex, beta_rad)
    ez /= np.linalg.norm(ez)

    # ------------------------------------------------------------------
    # 5) Local y from right-hand rule: y = z × x
    # ------------------------------------------------------------------
    ey = np.cross(ez, ex)
    norm_y = np.linalg.norm(ey)
    if norm_y < tol:
        raise RuntimeError("Failed to build a valid right-handed triad.")
    ey /= norm_y

    return LocalAxes(ex=ex, ey=ey, ez=ez)


# ---------------------------------------------------------------------------
# Low-level helper
# ---------------------------------------------------------------------------

def _rotate_around_axis(
    v: np.ndarray,
    axis: np.ndarray,
    angle_rad: float,
) -> np.ndarray:
    """
    Rotate vector v about 'axis' by 'angle_rad' (right-hand rule).

    Uses Rodrigues' rotation formula.
    """
    axis = np.asarray(axis, dtype=float)
    v = np.asarray(v, dtype=float)

    axis_norm = np.linalg.norm(axis)
    if axis_norm == 0.0:
        raise ValueError("Rotation axis has zero length.")

    k = axis / axis_norm
    c = math.cos(angle_rad)
    s = math.sin(angle_rad)

    return v * c + np.cross(k, v) * s + k * np.dot(k, v) * (1.0 - c)
