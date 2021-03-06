from __future__ import print_function

import time

from afem.config import Settings
from afem.geometry import *
from afem.graphics import Viewer
from afem.oml import Body
from afem.smesh import *
from afem.structure import *
from afem.topology import *

Settings.log_to_console()


def build_wingbox(wing, params):
    """
    Simple 2 spar wing box with mid spar and aux spar.
    """
    # Set units to inch.
    Settings.set_units('in')

    # SETUP -------------------------------------------------------------------
    _default = {'rib spacing': 30.,
                'fspar chord': 0.15,
                'rspar chord': 0.65,
                'root span': 0.05,
                'tip span': 0.925,
                'group name': 'RH main wingbox',
                'mid spar rib': 10,
                'root rib axes': 'xz',
                'part tol': 0.01,
                'build aux': True,
                'aux rib list': ['2', '5', '8'],
                'aux spar xloc': 0.85}

    for key in _default:
        if key not in params:
            params[key] = _default[key]

    # Unpack params.
    rib_spacing = params['rib spacing']
    fspar_chord = params['fspar chord']
    rspar_chord = params['rspar chord']
    root_span = params['root span']
    tip_span = params['tip span']
    group_name = params['group name']
    mid_spar_rib = params['mid spar rib']
    build_aux_spar = params['build aux']
    aux_rib_list = params['aux rib list']
    aux_spar_xloc = params['aux spar xloc']

    # BUILD -------------------------------------------------------------------
    GroupAPI.create_group(group_name)

    # Front spar
    fspar = SparByParameters('front spar', fspar_chord, root_span,
                             fspar_chord, tip_span, wing).part

    # Rear spar
    rspar = SparByParameters('rear spar', rspar_chord, root_span,
                             rspar_chord, tip_span, wing).part

    # Root rib
    p1 = fspar.p1
    if not build_aux_spar:
        p2 = rspar.p1
    else:
        p2 = wing.eval(aux_spar_xloc, root_span)
    root = RibByPoints('root rib', p1, p2, wing).part

    # Tip rib
    p1 = fspar.p2
    p2 = rspar.p2
    tip = RibByPoints('tip rib', p1, p2, wing).part

    # Generate points along rear spar and project to front spar to define ribs.
    prear = rspar.points_by_distance(rib_spacing, d1=rib_spacing,
                                     d2=-rib_spacing)
    pfront = [p.copy() for p in prear]
    rspar_norm = rspar.sref.norm(0, 0)
    fspar.points_to_cref(pfront, rspar_norm)
    i = 1
    ribs = []
    for pf, pr in zip(pfront, prear):
        if pf.is_equal(pr):
            continue
        name = ' '.join(['rib', str(i)])
        rib = RibByPoints(name, pf, pr, wing).part
        ribs.append(rib)
        i += 1

    # Build a mid spar.
    mspar = None
    if mid_spar_rib > 0:
        u1 = root.cref.u1
        u2 = root.invert_cref(rspar.p1)
        dx = root.cref.arc_length(u1, u2)
        p1 = root.point_from_parameter(dx / 2.)
        rib = ribs[mid_spar_rib - 1]
        p2 = rib.point_from_parameter(0.5, is_rel=True)
        mspar = SparByPoints('mid spar', p1, p2, wing).part

    # Aux spar.
    aspar = None
    if build_aux_spar:
        p1 = root.p2
        p2 = rspar.point_from_parameter(0.25, is_rel=True)
        # Find nearest rib point and set equal to aux spar.
        pnts = [rib.p2 for rib in ribs]
        p2 = CheckGeom.nearest_point(p2, pnts)
        indx = pnts.index(p2)
        rib = ribs[indx]
        # Use intersection of the rib and rear spar to define plane for aux
        # spar.
        sref = PlaneByIntersectingShapes(rspar.shape, rib.shape, p1).plane
        aspar = SparByPoints('aux spar', p1, p2, wing, sref).part

    # Build ribs from root rib to front spar.
    root_ribs = []
    if mspar:
        # Fwd of mid spar
        u2 = root.invert_cref(mspar.p1)
        builder = PointsAlongCurveByNumber(root.cref, 3, u2=u2)
        prib = builder.interior_points
        pfront = [p.copy() for p in prib]
        fspar.points_to_cref(pfront, rspar_norm)
        for pf, pr in zip(pfront, prib):
            if pf.is_equal(pr):
                continue
            name = ' '.join(['rib', str(i)])
            rib = RibByPoints(name, pf, pr, wing).part
            if not rib:
                continue
            ribs.append(rib)
            root_ribs.append(rib)
            i += 1

        # Aft of mid spar
        u1 = root.invert_cref(mspar.p1)
        u2 = root.invert_cref(rspar.p1)
        builder = PointsAlongCurveByNumber(root.cref, 3, u1=u1, u2=u2)
        prib = builder.interior_points
        pfront = [p.copy() for p in prib]
        fspar.points_to_cref(pfront, rspar_norm)
        for pf, pr in zip(pfront, prib):
            if pf.is_equal(pr):
                continue
            name = ' '.join(['rib', str(i)])
            rib = RibByPoints(name, pf, pr, wing).part
            if not rib:
                continue
            ribs.append(rib)
            root_ribs.append(rib)
            i += 1

    # Rib at intersection of rear spar and root rib. Use intersection and
    # projected point to define a plane.
    p2 = rspar.p1
    p1 = p2.copy()
    fspar.point_to_cref(p1, rspar_norm)
    sref = PlaneByIntersectingShapes(root.shape, rspar.shape, p1).plane
    RibByPoints('corner rib', p1, p2, wing, sref)

    # Construction geom for center structure.
    root_chord = wing.extract_curve(0, 0, 1, 0)

    # Front center spar.
    p2 = fspar.p1
    p1 = p2.copy()
    ProjectPointToCurve(p1, root_chord, update=True)
    SparByPoints('fc spar', p1, p2, wing)

    # Rear center spar.
    p2 = rspar.p1
    p1 = p2.copy()
    ProjectPointToCurve(p1, root_chord, update=True)
    SparByPoints('rc spar', p1, p2, wing)

    # Mid center spar
    if mid_spar_rib > 0:
        p2 = mspar.p1
        p1 = p2.copy()
        ProjectPointToCurve(p1, root_chord, update=True)
        SparByPoints('center mid spar', p1, p2, wing)

    # Center spar at each root rib intersection
    i = 1
    for rib in root_ribs:
        p2 = rib.p2
        p1 = p2.copy()
        name = ' '.join(['center spar', str(i)])
        ProjectPointToCurve(p1, root_chord, update=True)
        SparByPoints(name, p1, p2, wing)
        i += 1

    # Aux ribs
    if build_aux_spar:
        group = GroupAPI.get_active()
        aux_rib_id = 1
        for rib_id in aux_rib_list:
            rib_name = ' '.join(['rib', rib_id])
            rib = group.get_part(rib_name)
            if not rib:
                continue
            # Since the structure is not joined yet, intersect the rear spar
            # and rib shapes to find the edge(s). Use this edge to define a
            # plane so the aux ribs will line up with the main ribs.
            p1 = rib.p2
            p2 = p1.copy()
            aspar.point_to_cref(p2)
            sref = PlaneByIntersectingShapes(rspar.shape, rib.shape, p2).plane
            aux_rib_name = ' '.join(['aux rib', str(aux_rib_id)])
            RibByPoints(aux_rib_name, p1, p2, wing, sref)
            aux_rib_id += 1

    # JOIN --------------------------------------------------------------------
    # Fuse internal structure and discard faces
    internal_parts = GroupAPI.get_parts(order=True)
    FuseSurfacePartsByCref(internal_parts)
    DiscardByCref(internal_parts)

    # SKIN --------------------------------------------------------------------
    skin = SkinByBody('wing skin', wing, False).part
    skin.set_transparency(0.5)

    # Join the wing skin and internal structure
    skin.fuse(*internal_parts)

    # Discard faces touching reference surface.
    skin.discard_by_dmin(wing.sref_shape, 0.1)

    # Fix skin since it's not a single shell anymore, but a compound of two
    # shells (upper and lower skin).
    skin.fix()

    # Check free edges.
    all_parts = GroupAPI.get_parts(order=True)
    all_shapes = [part.shape for part in all_parts]

    # VOLUMES -----------------------------------------------------------------
    # Demonstrate creating volumes from shapes (i.e., parts). Do not use the
    # intersect option since shapes should be topologically connected already.

    # Volumes using all parts. This generates multiple solids.
    shape1 = VolumesFromShapes(all_shapes).shape

    # Volume using front spar, rear spar, root rib, tip rib, and upper and
    # lower skins. This should produce a single solid since no internal ribs
    #  are provided.
    shape2 = VolumesFromShapes([rspar.shape, fspar.shape, root.shape,
                                tip.shape, skin.shape]).shape
    # Calculate volume.
    print('Volume is ', VolumeProps(shape2).volume)

    # Create a semi-infinite box to cut volume with.
    p0 = wing.eval(0.5, 0.1)
    pln = PlaneByAxes(p0, 'xy').plane
    face = FaceByPlane(pln, -1500, 1500, -1500, 1500).face
    cut_space = ShapeByDrag(face, (0., 0., 500.)).shape

    # Cut the volume with an infinite plane (use a large box for robustness).
    new_shape = CutShapes(shape1, cut_space).shape

    # Calculate cg of cut shape.
    cg = VolumeProps(new_shape).cg
    print('Centroid of cut shape is ', cg)
    print('Volume of cut shape is ', VolumeProps(new_shape).volume)

    # Cut the volume with an infinite plane (use a large box for robustness).
    new_shape = CutShapes(shape2, cut_space).shape

    # Calculate cg of cut shape.
    cg = VolumeProps(new_shape).cg
    print('Centroid of cut shape is ', cg)
    print('Volume of cut shape is ', VolumeProps(new_shape).volume)

    # MESH --------------------------------------------------------------------
    # Initialize
    shape_to_mesh = GroupAPI.prepare_shape_to_mesh()
    the_gen = MeshGen()
    the_mesh = the_gen.create_mesh(shape_to_mesh)

    # Use a single global hypothesis based on maximum length.
    hyp1d = MaxLength1D(the_gen, 4.)
    alg1d = Regular1D(the_gen)
    the_mesh.add_hypotheses([hyp1d, alg1d], shape_to_mesh)

    # Netgen unstructured quad-dominated
    netgen_hyp = NetgenSimple2D(the_gen, 4.)
    netgen_alg = NetgenAlgo2D(the_gen)
    the_mesh.add_hypotheses([netgen_hyp, netgen_alg], shape_to_mesh)

    # Apply mapped quadrangle to internal structure
    mapped_hyp = QuadrangleHypo2D(the_gen)
    mapped_algo = QuadrangleAlgo2D(the_gen)
    for part_ in internal_parts:
        for face in part_.faces:
            if mapped_algo.is_applicable(face):
                the_mesh.add_hypotheses([mapped_algo, mapped_hyp], face)

    # Compute the mesh
    mesh_start = time.time()
    print('Computing mesh...')
    status = the_gen.compute(the_mesh, shape_to_mesh)
    if not status:
        print('Failed to compute mesh')
    else:
        print('Meshing complete in ', time.time() - mesh_start, ' seconds.')

    v.display_mesh(the_mesh.object, 2)
    v.start()
    v.clear()

    # Uncomment this to export STEP file.
    # from afem.io import StepExport
    # step = StepExport()
    # step.transfer(shape_to_mesh)
    # step.write('wingbox.step')

    return GroupAPI.get_active()


if __name__ == '__main__':
    start = time.time()

    # Import model
    fname = '../models/777-200LR.xbf'
    bodies = Body.load_bodies(fname)
    wing_in = bodies['Wing']

    v = Viewer()
    # Build wing box
    inputs = {'build aux': True,
              'mid spar rib': 10,
              'aux rib list': ['2', '5', '8']}
    group = build_wingbox(wing_in, inputs)

    v.add(group)
    v.start()

    print('Complete in ', time.time() - start, ' seconds.')
