from typing import List, Tuple
from random import shuffle, sample, randrange, choice
from copy import deepcopy
from multiprocessing import Pool, cpu_count
from common import transform_result, save_result, Instance, Library, score, get_scanable_books, GracefulKiller
import itertools
from time import time
import argparse
from sortings import sort_by_num_books_desc, sort_by_setup_time_asc, sort_by_sum_book_scores_desc


class Chromosome:

    mutation_probability = 0.75

    def __init__(self, instance: Instance):
        self.days = instance.days
        self.libraries = deepcopy(instance.libraries)  # initialize with random solution
        shuffle(self.libraries)
        self.split = 0
        self.score = 0
        self.calculate_split_and_score()

    def calculate_split_and_score(self):
        start = 0
        sc = 0
        books_scanned = set()
        for it, tup in enumerate(self.libraries):
            library = tup[1]
            books = get_scanable_books(library, self.days, start, books_scanned)
            if not books:
                library.books_chosen_num = 0
                continue
            else:
                self.split = it + 1

            sc += sum(list(map(lambda x: x[1], books)))
            books_scanned = books_scanned.union(set(books))
            library.books_chosen_num = len(books)
            start += library.signup
        self.score = sc

    def mutate(self):
        """
        mutation strategy version 1
        swap single library from above and below split point
        at this point algorithm always tries to apply mutation (probability of mutation is 1)
        :return:
        """
        self.calculate_split_and_score()
        libs = self.libraries.copy()
        a = randrange(0, self.split)
        b = randrange(self.split if self.split != len(self.libraries) else 0, len(self.libraries))
        libs[a], libs[b] = libs[b], libs[a]
        sc = score(libs, self.days, verbose=False)
        if sc > self.score:
            self.libraries = libs

    def reorder_libraries(self):
        """
        reorder libraries to move libraries with 0 books scanned to the end of the libraries list
        :return:
        """
        kickoffs = []
        for j in range(self.split):
            lib = self.libraries[j]
            if lib[1].books_chosen_num == 0:
                kickoffs.append(j)

        kickoffs.reverse()
        for j in kickoffs:
            self.libraries.append(self.libraries.pop(j))


class ChromosomeInitialized(Chromosome):

    def __init__(self, instance: Instance):
        self.days = instance.days
        self.libraries = deepcopy(instance.libraries)
        probs = []
        methods = [
            do_shuffle,
            do_shuffle,
            do_shuffle,
            sort_by_setup_time_asc,
            sort_by_num_books_desc,
            sort_by_sum_book_scores_desc
        ]
        m = choice(methods)
        self.libraries = m(self.libraries)
        self.split = 0
        self.score = 0
        self.calculate_split_and_score()


def do_shuffle(libraries: List[Tuple[int, Library]]) -> List[Tuple[int, Library]]:
    shuffle(libraries)
    return libraries


def tournament(chromosomes: List[Chromosome], k=4) -> Chromosome:
    chosen = sample(chromosomes, k)
    m = (0, 0)
    for it, c in enumerate(chosen):
        if c.score > m[1]:
            m = (it, c.score)
    return chosen[m[0]]


def crossover(a: Chromosome, b: Chromosome) -> Tuple[Chromosome, Chromosome]:
    ap = deepcopy(a)
    bp = deepcopy(b)
    # ap = a
    # ap.libraries = a.libraries.copy()
    # bp = b
    # bp.libraries = b.libraries.copy()
    ap.reorder_libraries()
    bp.reorder_libraries()
    # choose split point
    split = min(ap.split, bp.split)
    point = randrange(1, split)

    a_libs = ap.libraries[:point]
    a_ids = set(map(lambda x: x[0], a_libs))
    b_libs = bp.libraries[:point]
    b_ids = set(map(lambda x: x[0], b_libs))

    for it, l in bp.libraries:
        if it not in a_ids:
            a_libs.append((it, l))
    for it, l in ap.libraries:
        if it not in b_ids:
            b_libs.append((it, l))

    assert len(a_libs) == len(b_libs) == len(ap.libraries) == len(bp.libraries)
    ap.libraries = a_libs
    bp.libraries = b_libs

    return ap, bp


def tournament_and_crossover(chromosomes: List[Chromosome], k=4) -> Tuple[Chromosome, Chromosome]:
    a = tournament(chromosomes, k)
    b = tournament(chromosomes, k)
    return crossover(a, b)


def chromosome_factory(instance: Instance) -> Chromosome:
    return Chromosome(instance)

def chromosome_i_factory(instance: Instance) -> Chromosome:
    return ChromosomeInitialized(instance)


def flatten(pre_population: List[Tuple[Chromosome, Chromosome]]) -> List[Chromosome]:
    return list(itertools.chain.from_iterable(pre_population))


def mutate(c: Chromosome, times: int = 1) -> Chromosome:
    for _ in range(times):
        c.mutate()
        c.calculate_split_and_score()
    return c


def genetic(instance: Instance, size=64, iterations=10, k=4, mutations=5) -> List[Tuple[int, Library]]:
    """
    genetic algorithm version 1
    :param instance: instance object
    :param size: population size
    :param iterations: number of iterations
    :param k: tournament size
    :return:
    """
    monitor = GracefulKiller()
    p = Pool()
    chunksize = min(1, size//(cpu_count() * 2))
    population = p.map(chromosome_i_factory, [instance for _ in range(size)], chunksize=chunksize)
    result = deepcopy(population[0])
    cb = 0
    for pop in population:
            if pop.score > cb:
                cb = pop.score
            if pop.score > result.score:
                result = deepcopy(pop)

    print('Setup done')
    for iteration in range(iterations):
        start = time()
        pre = p.starmap(tournament_and_crossover, [(population, k) for _ in range(size//2)], chunksize=chunksize)
        population = flatten(pre)
        population = p.starmap(mutate, [(pop, mutations) for pop in population], chunksize=chunksize)
        # print(max(list(map(lambda x: x.score, population))))
        cb = 0
        for pop in population:
            if pop.score > cb:
                cb = pop.score
            if pop.score > result.score:
                result = deepcopy(pop)
        print(iteration, result.score, cb, len(set(map(lambda x: x.score, population))), time() - start, sep='\t')

        if monitor.kill_now:
            break

    return result.libraries
    

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description="Genetic algorithm to solve problem from round 1 of Google Hashcode 2020 competition")
    parser.add_argument('instance', type=str, choices=['a', 'b', 'c', 'd', 'e', 'f'], 
        help='Select instance to compute')
    parser.add_argument('-s', '--size', type=int, default=32, metavar='s', 
        help='Population size')
    parser.add_argument('-i', '--iterations', type=int, default=20, metavar='i', 
        help='Number of iterations')
    parser.add_argument('-k', '--tournament-size', type=int, default=4, metavar='k',
        help='Size of tournament')
    parser.add_argument('-m', '--mutations-count', type=int,  default=5, metavar='m',
        help='Number of attempts to mutate single element in the population in each iteration')
    args = parser.parse_args()

    index = ord(args.instance) - ord('a')

    files = ['a_example.txt',
             'b_read_on.txt',
             'c_incunabula.txt',
             'd_tough_choices.txt',
             'e_so_many_books.txt',
             'f_libraries_of_the_world.txt']
    file = files[index]
    print(file)

    i = Instance('input/' + file)
    print(i.num_books)
    print(score(i.libraries, i.days, verbose=False))
    print('--------')

    r = genetic(i, size=args.size, iterations=args.iterations, k=args.tournament_size, mutations=args.mutations_count)

    print('--------')
    print(score(r, i.days, verbose=False))
    save_result(transform_result(r, i.days), 'output/' + file[0] + '_genetic.out')
    print('Result saved. Done.')
