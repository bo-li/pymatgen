#!/usr/bin/env python

'''
This module defines standard transformations which transforms a structure into another structure.
All transformations should inherit the AbstractTransformation ABC.
'''

from __future__ import division

__author__ = "Shyue Ping Ong, Will Richards"
__copyright__ = "Copyright 2011, The Materials Project"
__version__ = "1.1"
__maintainer__ = "Shyue Ping Ong"
__email__ = "shyue@mit.edu"
__date__ = "Sep 23, 2011"

import json
import itertools
import warnings
import numpy as np
from operator import itemgetter

from pymatgen.transformations.transformation_abc import AbstractTransformation
from pymatgen.core.structure import Structure
from pymatgen.core.lattice import Lattice
from pymatgen.core.operations import SymmOp
from pymatgen.core.structure_modifier import StructureEditor, SupercellMaker, OxidationStateDecorator
from pymatgen.core.periodic_table import smart_element_or_specie
from pymatgen.analysis.ewald import EwaldSummation, EwaldMinimizer, minimize_matrix


class IdentityTransformation(AbstractTransformation):
    """
    This is a demo transformation which does nothing, i.e. just return the same structure.
    """

    def __init__(self):
        pass

    def apply_transformation(self, structure):
        return Structure(structure.lattice, structure.species_and_occu, structure.frac_coords)

    def __str__(self):
        return "Identity Transformation"

    def __repr__(self):
        return self.__str__()

    @property
    def inverse(self):
        return self

    @property
    def to_dict(self):
        output = {'name' : self.__class__.__name__, 'init_args': {}, 'version': __version__ }
        return output


class RotationTransformation(AbstractTransformation):
    """
    The RotationTransformation applies a rotation to a structure.
    """

    def __init__(self, axis, angle, angle_in_radians = False):
        """
        Arguments:
            axis - Axis of rotation, e.g., [1, 0, 0]
            angle - angle to rotate
            angle_in_radians - Set to True if angle is supplied in radians. Else degrees are assumed.
        """
        self._axis = axis
        self._angle = angle
        self._angle_in_radians = angle_in_radians
        self._symmop = SymmOp.from_axis_angle_and_translation(self._axis, self._angle, self._angle_in_radians)

    def apply_transformation(self, structure):
        editor = StructureEditor(structure)
        editor.apply_operation(self._symmop)
        return editor.modified_structure

    def __str__(self):
        return "Rotation Transformation about axis %s with angle = %.4f %s" % (str(self._axis), self._angle, "radians" if self._angle_in_radians else "degrees")

    def __repr__(self):
        return self.__str__()

    @property
    def inverse(self):
        return RotationTransformation(self._axis, -self._angle, self._angle_in_radians)

    @property
    def to_dict(self):
        output = {'name' : self.__class__.__name__, 'version': __version__}
        output['init_args'] = {'axis': self._axis, 'angle':self._angle, 'angle_in_radians':self._angle_in_radians}
        return output


class OxidationStateDecorationTransformation(AbstractTransformation):
    """
    This transformation decorates a structure with oxidation states.
    """

    def __init__(self, oxidation_states):
        """
        Args:
            oxidation_states
                Oxidation states supplied as a dict, e.g., {'Li':1, 'O':-2}
        """
        self.oxi_states = oxidation_states

    def apply_transformation(self, structure):
        dec = OxidationStateDecorator(structure, self.oxi_states)
        return dec.modified_structure

    @property
    def inverse(self):
        return None

    @property
    def to_dict(self):
        output = {'name' : self.__class__.__name__, 'version': __version__}
        output['init_args'] = {'oxidation_states': self.oxi_states}
        return output


class SupercellTransformation(AbstractTransformation):
    """
    The RotationTransformation applies a rotation to a structure.
    """

    def __init__(self, scaling_matrix = ((1, 0, 0), (0, 1, 0), (0, 0, 1))):
        """
        Args:
            scaling_matrix:
                Set to True if angle is supplied in radians. Else degrees are assumed.
        """
        self._matrix = scaling_matrix

    @staticmethod
    def from_scaling_factors(scale_a, scale_b, scale_c):
        """
        Convenience method to get a SupercellTransformation from a simple series
        of three numbers for scaling each lattice vector. Equivalent to calling
        the normal with [[scale_a, 0, 0], [0, scale_b, 0], [0, 0, scale_c]]
        
        Args:
            scale_a:
                Scaling factor for lattice direction a.
            scale_b:
                Scaling factor for lattice direction b.
            scale_c:
                Scaling factor for lattice direction c.
        """
        return SupercellTransformation([[scale_a, 0, 0], [0, scale_b, 0], [0, 0, scale_c]])

    def apply_transformation(self, structure):
        maker = SupercellMaker(structure, self._matrix)
        return maker.modified_structure

    def __str__(self):
        return "Supercell Transformation with scaling matrix %s" % (str(self._matrix))

    def __repr__(self):
        return self.__str__()

    @property
    def inverse(self):
        raise NotImplementedError()

    @property
    def to_dict(self):
        output = {'name' : self.__class__.__name__, 'version': __version__}
        output['init_args'] = {'scaling_matrix': self._matrix}
        return output


class SubstitutionTransformation(AbstractTransformation):
    """
    This transformation substitutes species for one another.
    """
    def __init__(self, species_map):
        """
        Args:
            species_map:
                A dict containing the species mapping in string-string pairs. 
                E.g., { "Li":"Na"} or {"Fe2+","Mn2+"}. Multiple substitutions can be done.
                Overloaded to accept sp_and_occu dictionary as second argument
                E.g. {'Si: {'Ge':0.75, 'C':0.25} }
        """
        self._species_map = species_map

    def apply_transformation(self, structure):
        species_map = {}
        for k, v in self._species_map.items():
            if isinstance(v, dict):
                value = {smart_element_or_specie(x):y for x, y in v.items()}
            else:
                value = smart_element_or_specie(v)
            species_map[smart_element_or_specie(k)] = value
        editor = StructureEditor(structure)
        editor.replace_species(species_map)
        return editor.modified_structure

    def __str__(self):
        return "Substitution Transformation :" + ", ".join([k + "->" + v for k, v in self._species_map.items()])

    def __repr__(self):
        return self.__str__()

    @property
    def inverse(self):
        return SubstitutionTransformation({v:k for k, v in self._species_map.items()})

    @property
    def to_dict(self):
        output = {'name' : self.__class__.__name__, 'version': __version__}
        output['init_args'] = {'species_map': self._species_map}
        return output


class RemoveSpeciesTransformation(AbstractTransformation):
    """
    Remove all occurrences of some species from a structure.
    """
    def __init__(self, species_to_remove):
        """
        Args:
            species_to_remove:
                List of species to remove. E.g., ["Li", "Mn"] 
        """
        self._species = species_to_remove

    def apply_transformation(self, structure):
        editor = StructureEditor(structure)
        map(editor.remove_species, [[smart_element_or_specie(sp)] for sp in self._species])
        return editor.modified_structure

    def __str__(self):
        return "Remove Species Transformation :" + ", ".join(self._species)

    def __repr__(self):
        return self.__str__()

    @property
    def inverse(self):
        return None

    @property
    def to_dict(self):
        output = {'name' : self.__class__.__name__, 'version': __version__}
        output['init_args'] = {'species_to_remove': self._species}
        return output


class PartialRemoveSpecieTransformation(AbstractTransformation):
    """
    Remove fraction of specie from a structure. 
    Requires an oxidation state decorated structure for ewald sum to be 
    computed.
    """
    def __init__(self, specie_to_remove, fraction_to_remove, complete_ranking = False):
        """
        Args:
            specie_to_remove:
                Specie to remove. Must have oxidation state E.g., "Li1+"
            fraction_to_remove:
                Fraction of specie to remove. E.g., 0.5
            complete_ranking:
                Whether to use the slow algorithm to enumerate all possible
                symmetrically distinct structures for energies. This populates
                the all_structures attribute, which provides access to all 
                structures.
        """
        self._specie = specie_to_remove
        self._frac = fraction_to_remove
        self._complete_ranking = complete_ranking

    def _optimize_ordering_slow_and_complete(self, structure, specie_indices, num_to_remove):
        lowestewald = float('inf')
        opt_s = None
        all_structures = list()
        from pymatgen.symmetry.spglib_adaptor import SymmetryFinder
        symprec = 0.1
        s = SymmetryFinder(structure, symprec = symprec)
        sg = s.get_spacegroup()
        tested_sites = []
        ewaldsum = EwaldSummation(structure)
        for indices in itertools.combinations(specie_indices, num_to_remove):
            sites_to_remove = [structure[i] for i in indices]
            already_tested = False
            for tsites in tested_sites:
                if sg.are_symmetrically_equivalent(sites_to_remove, tsites, symprec = symprec):
                    already_tested = True
            if not already_tested:
                tested_sites.append(sites_to_remove)
                mod = StructureEditor(structure)
                mod.delete_sites(indices)
                s_new = mod.modified_structure
                all_structures.append(s_new)
                energy = ewaldsum.compute_partial_energy(indices)
                if energy < lowestewald:
                    lowestewald = energy
                    opt_s = s_new

        return (opt_s, all_structures)

    def _optimize_ordering_fast(self, structure, specie_indices, num_to_remove):
        """
        This method uses the matrix form of ewaldsum to calculate the ewald sums 
        of the potential structures. This is on the order of 4 orders of magnitude 
        faster when there are large numbers of permutations to consider.
        There are further optimizations possible (doing a smarter search of 
        permutations for example), but this wont make a difference
        until the number of permutations is on the order of 30,000.
        """
        ewaldmatrix = EwaldSummation(structure).total_energy_matrix
        lowestenergy_indices = minimize_matrix(ewaldmatrix, specie_indices, num_to_remove)[1]
        mod = StructureEditor(structure)
        mod.delete_sites(lowestenergy_indices)
        return mod.modified_structure.get_sorted_structure()

    def apply_transformation(self, structure):
        sp = smart_element_or_specie(self._specie)
        num_to_remove = structure.composition[sp] * self._frac
        if abs(num_to_remove - int(num_to_remove)) > 1e-8:
            raise ValueError("Fraction to remove must be consistent with integer amounts in structure.")
        else:
            num_to_remove = int(round(num_to_remove))

        specie_indices = [i for i in xrange(len(structure)) if structure[i].specie == sp]

        if self._complete_ranking:
            (opt_s, self.all_structures) = self._optimize_ordering_slow_and_complete(structure, specie_indices, num_to_remove)
        else:
            opt_s = self._optimize_ordering_fast(structure, specie_indices, num_to_remove)
            self.all_structures = [opt_s]

        return opt_s

    def __str__(self):
        return "Remove Species Transformation :" + ", ".join(self._specie)

    def __repr__(self):
        return self.__str__()

    @property
    def inverse(self):
        return None

    @property
    def to_dict(self):
        output = {'name' : self.__class__.__name__, 'version': __version__}
        output['init_args'] = {'specie_to_remove': self._specie, 'fraction_to_remove': self._frac, 'complete_ranking':self._complete_ranking}
        return output


class OrderDisorderedStructureTransformation(AbstractTransformation):
    """
    Order a disordered structure. The disordered structure must be oxidation state decorated for ewald sum to be computed.
    No attempt is made to perform symmetry determination to reduce the number of combinations.
    Hence, attempting to performing ordering on a large number of disordered sites may be extremely expensive. The time scales approximately
    with the number of possible combinations. The algorithm can currently compute approximately 5,000,000 permutations per minute.
    There is also the initial cost of calculating the ewald sum (typically ~1 minute)
    
    Also, simple rounding of the occupancies are performed, with no attempt made to achieve a target composition.  This is usually not a problem
    for most ordering problems, but there can be times where rounding errors may result in structures that do not have the desired composition.
    This second step will be implemented in the next iteration of the code.
    
    If multiple fractions for a single species are found for different sites, these will be treated separately if the difference is above a
    threshold tolerance. currently this is .1
    For example, if a fraction of .25 Li is on sites 0,1,2,3  and .5 on sites 4,5,6,7 1 site from [0,1,2,3] will be filled
    and 2 sites from [4,5,6,7] will be filled, even though a lower energy combination might be found by putting all lithium in
    sites [4,5,6,7]
    
    USE WITH CARE.
    """
    def __init__(self, num_structures = 1, mev_cutoff = None):
        '''
        Args:
            num_structures: maximum number of structures to return
            mev_cutoff: maximum mev per atom above the minimum energy ordering for a structure to be returned
        '''
        
        self._mev_cutoff = mev_cutoff
        self._all_structures = []
        self._num_structures = num_structures

    def apply_transformation(self, structure):
        """
        For this transformation, the apply_transformation method will return only the ordered
        structure with the lowest Ewald energy, to be consistent with the method signature of the other transformations.  
        However, all structures are stored in the  all_structures attribute in the transformation object for easy access.
        
        Args:
            structure:
                Oxidation state decorated disordered structure to order
        """
        ordered_sites = []
        sites_to_order = {}

        sites = list(structure.sites)
        for i in range(len(structure)):
            site = sites[i]
            if sum(site.species_and_occu.values()) == 1 and len(site.species_and_occu) == 1:
                ordered_sites.append(site)
            else:
                species = tuple([sp for sp, occu in site.species_and_occu.items()])     #group the sites by the list of species
                                                                                        #on that site
                for sp, occu in site.species_and_occu.items():
                    if species not in sites_to_order:
                        sites_to_order[species] = {}
                    if sp not in sites_to_order[species]:
                        sites_to_order[species][sp] = [[occu, i]]
                    else:
                        sites_to_order[species][sp].append([occu, i])

                total_occu = sum(site.species_and_occu.values())        #if the total occupancy on a site is less than one, add
                if total_occu < 1:                                      #a list with None as the species (for removal)
                    if None not in sites_to_order[species]:
                        sites_to_order[species][None] = [[1 - total_occu, i]]
                    else:
                        sites_to_order[species][None].append([1 - total_occu, i])

        m_list = []     #create a list of [multiplication fraction, number of replacements, [indices], replacement species]
        se = StructureEditor(structure)


        for species in sites_to_order.values():
            initial_sp = None
            sorted_keys = sorted(species.keys(), key = lambda x: x is not None and -abs(x.oxi_state) or 1000)
            for sp in sorted_keys:
                if initial_sp is None:
                    initial_sp = sp
                    for site in species[sp]:
                        se.replace_single_site(site[1], species = initial_sp)
                else:
                    if sp is None:
                        oxi = 0
                    else:
                        oxi = float(sp.oxi_state)

                    manipulation = [oxi / initial_sp.oxi_state, 0, [], sp]
                    site_list = species[sp]
                    site_list.sort(key = itemgetter(0))

                    prev_fraction = site_list[0][0]
                    for site in site_list:
                        if site[0] - prev_fraction > .1:            #tolerance for creating a new group of sites. 
                                                                    #if site occupancies are similar, they will be put in a group
                                                                    #where the fraction has to be consistent over the whole
                            manipulation[1] = int(round(manipulation[1]))
                            m_list.append(manipulation)
                            manipulation = [oxi / initial_sp.oxi_state, 0, [], sp]
                        prev_fraction = site[0]
                        manipulation[1] += site[0]
                        manipulation[2].append(site[1])

                    manipulation[1] = int(round(manipulation[1]))
                    m_list.append(manipulation)

        structure = se.modified_structure

        matrix = EwaldSummation(structure).total_energy_matrix

        ewald_m = EwaldMinimizer(matrix, m_list, self._num_structures)

        self._all_structures = []

        for output in ewald_m.output_lists:
            se = StructureEditor(structure)
            del_indices = [] #do deletions afterwards because they screw up the indices of the structure

            for manipulation in output[1]:
                if manipulation[1] is None:
                    del_indices.append(manipulation[0])
                else:
                    se.replace_single_site(manipulation[0], species = manipulation[1])
            se.delete_sites(del_indices)
            self._all_structures.append([output[0], se.modified_structure.get_sorted_structure()])
        
        if self._mev_cutoff is not None: #remove structures from all_structures list if they dont meet the mev cutoff requirements
            self._all_structures = [x for x in self._all_structures if x[0] < self._all_structures[0][0] + len(self._all_structures[0][1]) * self._mev_cutoff/1000 ]

        return [self._all_structures[i][1] for i in range(len(self._all_structures))]

    def __str__(self):
        return "Order disordered structure transformation"

    def __repr__(self):
        return self.__str__()

    @property
    def inverse(self):
        return None

    @property
    def to_dict(self):
        output = {'name' : self.__class__.__name__, 'version': __version__}
        output['init_args'] = {'num_structures' : self._num_structures, 'mev_cutoff' : self._mev_cutoff}
        return output

    @property
    def all_structures(self):
        return self._all_structures



class OrderDisorderedStructureTransformation_old(AbstractTransformation):
    """
    Order a disordered structure. The disordered structure must be oxidation state decorated for ewald sum to be computed.
    Please note that the current form uses a "dumb" algorithm of completely enumerating all possible combinations of
    partially occupied sites.  No attempt is made to perform symmetry determination to reduce the number of combinations.
    Hence, attempting to performing ordering on a large number of disordered sites may be extremely expensive.  Also, simple
    rounding of the occupancies are performed, with no attempt made to achieve a target composition.  This is usually not a problem
    for most ordering problems, but there can be times where rounding errors may result in structures that do not have the desired composition.
    This second step will be implemented in the next iteration of the code. USE WITH CARE.
    """
    def __init__(self):
        pass

    def apply_transformation(self, structure, max_iterations = 100):
        """
        For this transformation, the apply_transformation method will return only the ordered
        structure with the lowest Ewald energy, to be consistent with the method signature of the other transformations.  
        However, all structures are stored in the all_structures attribute in the transformation object for easy access.
        
        Args:
            structure:
                Oxidation state-decorated disordered structure to order
            max_iterations:
                Maximum number of structures to consider. Defaults to 100. This is useful if there are a large number of sites 
                and there are too many orderings to enumerate.
        """
        ordered_sites = []

        sites_to_order = {}
        for site in structure:
            species_and_occu = site.species_and_occu
            if sum(species_and_occu.values()) == 1 and len(species_and_occu) == 1:
                ordered_sites.append(site)
            else:
                spec = tuple([(sp, occu) for sp, occu in species_and_occu.items()])
                if spec not in sites_to_order:
                    sites_to_order[spec] = [site]
                else:
                    sites_to_order[spec].append(site)

        allselections = []
        species = []
        for spec, sites in sites_to_order.items():
            total_sites = len(sites)
            for (sp, fraction) in spec:
                num_to_select = int(round(fraction * total_sites))
                if num_to_select == 0:
                    raise ValueError("Fraction not consistent with selection of at least a single site.  Make a supercell before proceeding further.")
                allselections.append(itertools.combinations(sites, num_to_select))
                species.append(sp)

        all_ordered_s = {}
        count = 0

        def in_coords(allcoords, coord):
            for test_coord in allcoords:
                if all(coord == test_coord):
                    return True
            return False

        for selection in itertools.product(*allselections):
            all_species = [site.species_and_occu for site in ordered_sites]
            all_coords = [site.frac_coords for site in ordered_sites]

            contains_dupes = False
            for i in xrange(len(selection)):
                subsel = selection[i]
                sp = species[i]
                for site in subsel:
                    if not in_coords(all_coords, site.frac_coords):
                        all_species.append(sp)
                        all_coords.append(site.frac_coords)
                    else:
                        contains_dupes = True
                        break
                if contains_dupes:
                    break

            if not contains_dupes:
                s = Structure(structure.lattice, all_species, all_coords, False).get_sorted_structure()
                ewaldsum = EwaldSummation(s)
                ewald_energy = ewaldsum.total_energy
                all_ordered_s[s] = ewald_energy
                count += 1
                if count == max_iterations:
                    warnings.warn("Maximum number of iterations reached.  Structures will be ordered based on " + str(max_iterations) + " structures.")
                    break

        self.all_structures = all_ordered_s
        sorted_structures = sorted(all_ordered_s.keys(), key = lambda a: all_ordered_s[a])

        return sorted_structures[0]

    def __str__(self):
        return "Order disordered structure transformation"

    def __repr__(self):
        return self.__str__()

    @property
    def inverse(self):
        return None

    @property
    def to_dict(self):
        output = {'name' : self.__class__.__name__, 'version': __version__}
        output['init_args'] = {}
        return output


class PrimitiveCellTransformation(AbstractTransformation):
    """
    This class finds the primitive cell of the input structure. 
    It returns a structure that is not necessarily orthogonalized
    Author: Will Richards
    """
    def __init__(self, tolerance = 0.2):
        self._tolerance = tolerance

    def _get_more_primitive_structure(self, structure, tolerance):
        '''this finds a smaller unit cell than the input
        sometimes it doesn't find the smallest possible one, so this method is called until it
        is unable to find a smaller cell
        
        The method works by finding transformational symmetries for all sites and then using
        that translational symmetry instead of one of the lattice basis vectors
        if more than one vector is found (usually the case for large cells) the one with the 
        smallest norm is used
        
        Things are done in fractional coordinates because its easier
        to translate back to the unit cell'''

        #convert tolerance to fractional coordinates
        tol_a = tolerance / structure.lattice.a
        tol_b = tolerance / structure.lattice.b
        tol_c = tolerance / structure.lattice.c

        #get the possible symmetry vectors
        sites = sorted(structure.sites, key = lambda site: site.species_string)
        grouped_sites = [list(group) for k, group in itertools.groupby(sites, key = lambda site: site.species_string)]
        min_site_list = min(grouped_sites, key = lambda group: len(group))

        x = min_site_list[0]
        possible_vectors = []
        for y in min_site_list:
            if not x == y:
                vector = (x.frac_coords - y.frac_coords) % 1
                possible_vectors.append(vector)

        #test each vector to make sure its a viable vector for all sites
        for x in sites:
            for j in range(len(possible_vectors)):
                p_v = possible_vectors[j]
                fit = False
                if p_v is not None: #have to test that adding vector to a site finds a similar site
                    test_location = x.frac_coords + p_v
                    possible_locations = [site.frac_coords for site in sites if site.species_and_occu == x.species_and_occu and not x == site]
                    for p_l in possible_locations:
                        diff = .5 - abs((test_location - p_l) % 1 - .5)
                        if diff[0] < tol_a and diff[1] < tol_b and diff[2] < tol_c:
                            fit = True
                            break
                    if not fit:
                        possible_vectors[j] = None

        #vectors that haven't been removed from possible_vectors are symmetry vectors
        #convert these to the shortest representation of the vector           
        symmetry_vectors = [.5 - abs((x - .5) % 1) for x in possible_vectors if x is not None]
        if symmetry_vectors:
            reduction_vector = min(symmetry_vectors, key = np.linalg.norm)

            #choose a basis to replace (a, b, or c)
            proj = abs(structure.lattice.abc * reduction_vector)
            basis_to_replace = list(proj).index(max(proj))

            #create a new basis
            new_matrix = structure.lattice.matrix
            new_basis_vector = np.dot(reduction_vector, new_matrix)
            new_matrix[basis_to_replace] = new_basis_vector
            new_lattice = Lattice(new_matrix)

            #create a structure with the new lattice
            new_structure = Structure(new_lattice, structure.species_and_occu,
                                      structure.cart_coords, coords_are_cartesian = True)

            #update sites and tolerances for new structure
            sites = list(new_structure.sites)

            tol_a = tolerance / new_structure.lattice.a
            tol_b = tolerance / new_structure.lattice.b
            tol_c = tolerance / new_structure.lattice.c

            #Make list of unique sites in new structure
            new_sites = []
            for site in sites:
                fit = False
                for new_site in new_sites:
                    if site.species_and_occu == new_site.species_and_occu:
                        diff = .5 - abs((site.frac_coords - new_site.frac_coords) % 1 - .5)
                        if diff[0] < tol_a and diff[1] < tol_b and diff[2] < tol_c:
                            fit = True
                            break
                if not fit:
                    new_sites.append(site)

            #recreate the structure with just these sites
            new_structure = Structure(new_structure.lattice, [site.species_and_occu for site in new_sites],
                                  [(site.frac_coords + .001) % 1 - .001 for site in new_sites])

            return new_structure
        else: #if there were no translational symmetry vectors
            return structure

    def apply_transformation(self, structure):
        structure2 = self._get_more_primitive_structure(structure, self._tolerance)
        while len(structure2) < len(structure):
            structure = structure2
            structure2 = self._get_more_primitive_structure(structure, self._tolerance)
        return structure2


    def __str__(self):
        return "Primitive cell transformation"

    def __repr__(self):
        return self.__str__()

    @property
    def inverse(self):
        return None

    @property
    def to_dict(self):
        output = {'name' : self.__class__.__name__, 'version': __version__}
        output['init_args'] = {}
        return output


class TranslateSitesTransformation(AbstractTransformation):
    """
    This class translates a set of sites by a certain vector.
    """
    def __init__(self, indices_to_move, translation_vector, vector_in_frac_coords = True):
        self._indices = indices_to_move
        self._vector = translation_vector
        self._frac = vector_in_frac_coords

    def apply_transformation(self, structure):
        editor = StructureEditor(structure)
        editor.translate_sites(self._indices, self._vector, self._frac)
        return editor.modified_structure

    def __str__(self):
        return "TranslateSitesTransformation for indices {}, vector {} and vector_in_frac_coords = {}".format(self._indices, self._translation_vector, self._frac)

    def __repr__(self):
        return self.__str__()

    @property
    def inverse(self):
        return TranslateSitesTransformation(self._indices, [-c for c in self._vector], self._frac)

    @property
    def to_dict(self):
        output = {'name' : self.__class__.__name__, 'version': __version__}
        output['init_args'] = {'indices_to_move': self._indices,
                               'translation_vector': self._vector,
                               'vector_in_frac_coords': self._frac}
        return output


def transformation_from_dict(d):
    """
    A helper function that can simply get a transformation from a json representation.
    
    Arguments:
        json_string:
            A json string representation of a transformation with init args.
    
    Returns:
        A properly initialized Transformation object
    """
    trans = globals()[d['name']]
    return trans(**d['init_args'])


def transformation_from_json(json_string):
    """
    A helper function that can simply get a transformation from a json representation.
    
    Arguments:
        json_string:
            A json string representation of a transformation with init args.
    
    Returns:
        A properly initialized Transformation object
    """
    jsonobj = json.loads(json_string)
    return transformation_from_dict(jsonobj)
