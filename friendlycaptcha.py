# -*- coding: utf-8 -*-

import struct
import math
import base64
import datetime
import hashlib
import multiprocessing

import json
import requests

NUMBER_OF_PUZZLES_OFFSET = 14
PUZZLE_DIFFICULTY_OFFSET = 15
PUZZLE_EXPIRY_OFFSET = 13

HASH_SIZE_BYTES = 32
CHALLENGE_SIZE_BYTES = 128
NUMWORKERS = 8

class FriendlyCaptcha():

    def difficultyToThreshold(self, value):
        if value > 255:
            value = 255
        elif value < 0:
            value = 0
        return int(math.pow(2, (255.999 - value) / 8.0))


    def decodeBase64Puzzle(self, puzzle_raw):
        parts = puzzle_raw.split(".")
        puzzle = parts[1]
        arr = base64.b64decode(puzzle)
        return {
            "signature": parts[0],
            "base64": puzzle,
            "buffer": arr,
            "n": arr[NUMBER_OF_PUZZLES_OFFSET],
            "threshold": self.difficultyToThreshold(arr[PUZZLE_DIFFICULTY_OFFSET]),
            "expiry": arr[PUZZLE_EXPIRY_OFFSET] * 300000,
        }

    def getPuzzleSolverInputs(self, puzzleBuffer, numPuzzles):
        startingPoints = []

        for i in range(numPuzzles):
            input = [0] * CHALLENGE_SIZE_BYTES
            input = [(puzzleBuffer[n] if n < len(puzzleBuffer) else input[n]) for n in range(len(input))]
            
            input[120] = i
            startingPoints.append(input)
        
        return startingPoints

    def start(self, puzzle_raw):
        puzzle = self.decodeBase64Puzzle(puzzle_raw)
        puzzleSolverInputs = self.getPuzzleSolverInputs(puzzle['buffer'], puzzle['n'])
        solutionBuffer = [0] * (8 * puzzle['n'])

        workers = [None] * NUMWORKERS
        results = multiprocessing.Manager().dict()

        startTime = datetime.datetime.now()

        for i in range(NUMWORKERS):
            data = {
                'type': "start",
                'puzzleSolverInputs': puzzleSolverInputs,
                'threshold': puzzle['threshold'],
                'n': puzzle['n'],
                'numWorkers': NUMWORKERS,
                'startIndex': i
            }
            workers[i] = Worker(data, results)
            workers[i].start()

        for i in range(NUMWORKERS):
            workers[i].join()
        
        for i in range(NUMWORKERS):
            solutionBuffer = self.appendToSolutionBuffer(solutionBuffer, puzzleSolverInputs, i, results[i])
        
        totalTime = (datetime.datetime.now() - startTime).seconds
        diagnostics = self.createDiagnosticsBuffer(2, totalTime)

        str = f'{puzzle["signature"]}.{puzzle["base64"]}.{self.base64of(solutionBuffer)}.{self.base64of(diagnostics)}'
        
        return str

    def appendToSolutionBuffer(self, solutionBuffer, puzzleSolverInputs, startIndex, solution):
        t = startIndex
        while t < len(puzzleSolverInputs):
            sol = solution[(t * 8) : ((t * 8) + 8)]
            for s in range(len(solutionBuffer)):
                if s >= 8 * t and s < 8 * t + 8:
                    solutionBuffer[s] = sol[s- 8*t]
            t += NUMWORKERS
        return solutionBuffer

    def createDiagnosticsBuffer(self, solverID: int, timeToSolved: int):
        arr = bytearray([0] * 3)
        arr[0] = solverID
        struct.pack_into('>H', arr, 1, timeToSolved)

        return arr
    
    def base64of(self, value):
        return base64.b64encode(bytes(value)).decode('utf8')

class Worker(multiprocessing.Process):

    def __init__(self, data, results):
        multiprocessing.Process.__init__(self)
        self.data = data
        self.results = results

    def run(self):
        totalH = 0
        starts = self.data['puzzleSolverInputs']
        solutionBuffer = [0] * (8 * self.data['n'])

        puzNum = self.data['startIndex']
        while puzNum < len(starts):
            solution = []

            for b in range(256):
                starts[puzNum][123] = b
                s, hash = self.solve(starts[puzNum], self.data['threshold'])
                if len(hash) == 0:

                    print('FC: Internal error or no solution found')
                    totalH += math.pow(2, 32) - 1
                    continue
                solution = s
                break
                
            solution = solution[-8:]
            solutionBuffer = [solution[n-puzNum * 8] if (n >= puzNum * 8) & (n < puzNum*8 + 8) else solutionBuffer[n] for n in range(len(solutionBuffer))]
            puzNum += self.data['numWorkers']

        self.results[self.data['startIndex']] = solutionBuffer

    def solve(self, puzzleBuffer, threshold, n = 4294967295):
        puzzleBuffer, hash = self.solveBlake2bEfficient(puzzleBuffer, threshold, n)
        return puzzleBuffer, hash

    def solveBlake2bEfficient(self, input, threshold, n):
        if len(input) != CHALLENGE_SIZE_BYTES:
            print('Invalid input')

        input = bytearray(input)

        start = self.getuint32(124, input)
        end = start + n

        for i in range(start, end):
            self.setuint32(124, i, input)

            hash = hashlib.blake2b(input, digest_size=32).digest()
            h0 = self.getuint32(0, hash)

            if h0 < threshold:
                return input, hash

        return input, []

    def setuint32(self, index, v, input):
        struct.pack_into('<I', input, index, v)

    def getuint32(self, index, input):
        return struct.unpack_from("<I", input, index)[0]




def askforPuzzle(siteKey: str, url: str):

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/57.0.2987.98 Safari/537.36 OPR/44.0.2510.857',
        'Accept': '*/*',
        'Accept-Language': 'de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'sec-ch-ua': '" Not;A Brand";v="99", "Google Chrome";v="97", "Chromium";v="97"',
        'sec-ch-us-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-site': 'same-origin',
        'sec-fetch-mode': 'cors',
        'sec-fetch-dest': 'empty',
        'dnt': '1',
        'x-frc-client': 'js-0.9.0'
    }

    try:
        res = requests.get(url, headers=headers, params={'sitekey': siteKey})
    except:
        print('IP got blocked from FriendlyCaptcha!')

    try:
        js = json.loads(res.text)
        puzzle = js['data']['puzzle']
        return puzzle
    except:
        print('Error getting Puzzle! Retrying...')

def solvePuzzle(puzzle: str):
    start_time = datetime.datetime.now()
    fc = FriendlyCaptcha()
    solution = fc.start(puzzle)
    end_time = datetime.datetime.now()
    print(f'Puzzle solved in {(end_time-start_time).seconds}s')
    return solution
            