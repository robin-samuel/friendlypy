# -*- coding: utf-8 -*-

import friendlycaptcha as fc

if __name__ == "__main__":

    puzzle = fc.askforPuzzle('FCMTJL2D38C279E8', 'https://api.friendlycaptcha.com/api/v1/puzzle')
    print(f'Puzzle: {puzzle}')
    solution = fc.solvePuzzle(puzzle)
    print(f'Solution: {solution}')