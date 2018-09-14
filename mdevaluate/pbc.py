
from collections import OrderedDict

import numpy as np
import numba

from scipy.spatial import cKDTree

from .logging import logger

def pbc_diff_old(v1, v2, box):
    """
    Calculate the difference of two vestors, considering optional boundary conditions.
    """
    if box is None:
        v = v1 - v2
    else:
        v = v1 % box - v2 % box
        v -= (v > box / 2) * box
        v += (v < -box / 2) * box

    return v


def pbc_diff(v1, v2=None, box=None):
    """
    Calculate the difference of two vectors, considering periodic boundary conditions.
    """
    if v2 is None:
        v = v1
    else:
        v = v1 -v2
    if box is not None:
        s = v / box
        v = box * (s - s.round())
    return v


@numba.jit(nopython=True)
def pbc_diff_numba(ri, rj, box):
    v = ri % box - rj % box
    v -= (v > box / 2) * box
    v += (v < -box / 2) * box
    return v


def whole(frame):
    """
    Apply ``-pbc whole`` to a CoordinateFrame.
    """
    residue_ids = frame.coordinates.atom_subset.residue_ids
    box = frame.box.diagonal()
    coms = np.array([
        np.bincount(residue_ids, weights=c * frame.masses)[1:] / np.bincount(residue_ids, weights=frame.masses)[1:]
        for c in frame.T
    ]).T[residue_ids - 1]

    cor = np.zeros_like(frame)
    cd = frame - coms
    n, d = np.where(cd > box / 2 * 0.9)
    cor[n, d] = -box[d]
    n, d = np.where(cd < -box / 2 * 0.9)
    cor[n, d] = box[d]

    duomask = np.bincount(residue_ids)[1:][residue_ids - 1] == 2
    if np.any(duomask):
        duomask[::2] = False
        cor[duomask] = 0

    return frame + cor


NOJUMP_CACHESIZE = 128


def nojump(frame, usecache=True):
    """
    Return the nojump coordinates of a frame, based on a jump matrix.
    """
    selection = frame.coordinates.atom_subset.selection

    reader = frame.coordinates.frames
    if usecache:
        if not hasattr(reader, '_nojump_cache'):
            reader._nojump_cache = OrderedDict()
        i0s = [x for x in reader._nojump_cache if x <= frame.step]
        if len(i0s) > 0:
            i0 = max(i0s)
            delta = reader._nojump_cache[i0]
            i0 += 1
        else:
            i0 = 0
            delta = 0

        delta += np.array(np.vstack(
            [m[i0:frame.step + 1].sum(axis=0) for m in frame.coordinates.frames.nojump_matrixes]
        ).T) * frame.box.diagonal()

        reader._nojump_cache[frame.step] = delta
        while len(reader._nojump_cache) > NOJUMP_CACHESIZE:
            reader._nojump_cache.popitem(last=False)
        delta = delta[selection, :]
    else:
        delta = np.array(np.vstack(
            [m[:frame.step + 1, selection].sum(axis=0) for m in frame.coordinates.frames.nojump_matrixes]
        ).T) * frame.box.diagonal()
    return frame - delta


def pbc_points(coordinates, box, thickness=0, index=False, inclusive=True, center=None):
    """
    Returns the points their first periodic images. Does not fold them back into the box.
    Thickness 0 means all 27 boxes. Positive means the box+thickness. Negative values mean that less than the box is returned.
    index=True also returns the indices with indices of images being their originals values.
    inclusive=False returns only images, does not work with thickness <= 0
    """
    if center is None:
        center = box/2
    allcoordinates = np.copy(coordinates)
    indices = np.tile(np.arange(len(coordinates)),(27))
    for x in range(-1, 2, 1):
            for y in range(-1, 2, 1):
                for z in range(-1, 2, 1):
                    vv = np.array([x, y, z], dtype=float)
                    if not (vv == 0).all() :
                        allcoordinates = np.concatenate((allcoordinates, coordinates + vv*box), axis=0)
    
    if thickness != 0:
        mask = np.all(allcoordinates < center+box/2+thickness, axis=1)
        allcoordinates = allcoordinates[mask]
        indices = indices[mask]
        mask = np.all(allcoordinates > center-box/2-thickness, axis=1)
        allcoordinates = allcoordinates[mask]
        indices = indices[mask]
    if not inclusive and thickness > 0:
        allcoordinates = allcoordinates[len(coordinates):]
        indices = indices[len(coordinates):]
    if index:
        return (allcoordinates, indices)
    return allcoordinates
