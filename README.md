[![Pipeline status on GitLab CI][pipeline-badge]][pipeline-link]

# Graph-based Android Pattern Brute Force
A tool for brute forcing an Android security pattern through TWRP recovery based on a graph-traversal model (credit to https://github.com/psarna).

During a holiday trip my phone did a dive too deep and the screen broke. By the time the screen was fixed I had forgotten what security pattern I had set. But I remembered some parts of my pattern and used Tim's code (timvisee/apbf) and Piotrs help to build a python version of apbf.
I succeeded to crack my 5x5 pattern in about XX.XX hours (at the time of writing it's still running on a small Linux Mint machine...will update if/when successful).

## Requirements
- A pattern lock
- Android 8.0 (Nougat) or above
- [TWRP][twrp] recovery
- [`adb`][adb] (with connectivity to phone in TWRP) [direct platform-tools download link](https://developer.android.com/tools/releases/platform-tools)
- [`git`][git]
- [`python`](https://www.python.org/) v3.11.4 or higher

## Speed
TWRP recovery enforces a hidden timeout of 10 seconds for each pattern attempt,
all consecutive attempts within that time fail with no warning. Because of this
a brute force attempt will take a long while when the pattern search space is
large.

It is highly recommended to constrain the search space as much as possible if
you partially know the pattern to greatly improve the brute force duration.

This tool does brute forcing on the actual device. A brute force attempt could
probably be greatly sped up by performing the attempt locally on a computer,
to work around the timeouts. That's however a lot more work to implement (if
even possible), so it's outside the scope of this project.
## Configuration
In the [`config.yaml`](./config.yaml) file you can tweak a few constants for:
- Grid size
- Minimum pattern length
- Maximum pattern length
- Maximum path node distance
- Path prefix
- Path suffix
- Nodes to exclude
- Delay between attempts

### Grid size 
The grid size is defined by the number of nodes in the grid. As of writing Android supports 3, 4, 5, and 6 sides grids. The default is 3.
Each grid is repesented by a list of lists. The first list is the top row, the second list is the middle row, and the third list is the bottom row. The nodes are numbered from left to right, top to bottom starting at 1.
This grid is based on the [note on TWRP decrypt pattern](https://twrp.me/faq/openrecoveryscript.html) and more information here [from Alex Xu's blog](https://blog.alxu.ca/unlocking-large-pattern-encryption-in-twrp.html) and [the TWRP code base](https://github.com/TeamWin/Team-Win-Recovery-Project/blob/android-6.0/gui/patternpassword.cpp#L417)The default grid is a 3x3 grid with nodes 1-9.

It looks like this:
```
[
    [1, 2, 3],
    [4, 5, 6],
    [7, 8, 9]
]
```



The 4x4 grid looks like this:
```
[
    [1, 2, 3, 4],
    [5, 6, 7, 8],
    [9, :, ;, <],
    [=, >, ?, @]
]
```

The 5x5 grid looks like this:
```
[
    [1, 2, 3, 4, 5],
    [6, 7, 8, 9, :],
    [;, <, =, >, ?],
    [@, A, B, C, D],
    [E, F, G, H, I]
]
```
**I could not find information on the 6x6 pattern. Feel free to make a commit!**
My *assumption* is that the 6x6 grid looks like this:
```
[
    [1, 2, 3, 4, 5, 6],
    [7, 8, 9, :, ;, <],
    [=, >, ?, @, A, B],
    [C, D, E, F, G, H],
    [I, J, K, L, M, N],
    [O, P, Q, R, S, T]
]
```


## Usage
- Make sure you meet the [requirements](#requirements)
- Clone the repository, and build the project
  ```bash
  # Clone repository
  git clone git@github.com:robsteward/gapbf.git
  cd gapbf
  ```

- Install required modules
  ```bash
  pip3 install PyYAML
  ```

- Tweak properties in [`config.yaml`](./config.yaml):
  ```bash
  # Edit configuration
  code config.yaml
  ```

  Constrain it as much as possible to reduce pattern search space, which greatly
  improves brute force speed. See [speed](#speed).

- Freshly boot phone into TWRP recovery
- Make sure your phone is connected through ADB
  ```bash
  # Device must be visible in list
  adb devices
  ```

- Start brute forcing
  ```bash
  # Run tool
  python3 main.py [-m {{modes}}]
  ```

- Wait for a successful attempt. **This may take a long while**
- If the program gets interrupted, check the log file for the last successful attempt
  ```bash
  # Check log file
  cat log.csv
  ```

## Config
In the config.yaml file you can tweak a few constants for:
- Grid size
- Minimum pattern length
- Maximum pattern length
- Path prefix
- Path suffix
- Nodes to exclude
- Delay between attempts

## To Do
* ~~Update and verify grid neighbors in config.yaml~~
* ~~Convert config to yaml file~~
* ~~Move grids to GraphHandler~~
* ~~Write ConfigHandler class~~
* ~~Test DummyHandler~~
* ~~In ADBHandler read attemptedPaths csv to set and check current path against attemptedPaths and skip if found~~
* ~~Replace grid with predefined substistued grids (3,4,5,6)~~
* ~~Remove substitue function~~
* ~~Build CountPathHandler~~
* ~~Move DFS variable reading/parameters to class level~~
* ~~Implement testing framework (pytest)~~
* ~~Write tests (unit test, integration test)~~
* ~~Order handlers (ADB, iOS, Print, Test, Log)~~
* Fix logging to file from ADB handler)
* ~~Fix PrintHandler not showing correct path~~
* Fix dfs not respecting config min/max path length and excluding nodes, and path prefix/suffix
* Improve error handling
* ~~Add documentation~~
* ~~Verify tests~~
* ~~Make config loading consistent and efficient (config object, class assignment, vs direct loading)~~

## License
This project is released under the GNU GPL-3.0 license.
Check out the [LICENSE](LICENSE) file for more information.

[adb]: https://developer.android.com/studio/command-line/adb
[git]: https://git-scm.com/
[twrp]: https://twrp.me/
[pipeline-badge]: https://gitlab.com/timvisee/apbf/badges/master/pipeline.svg
[pipeline-link]: https://gitlab.com/timvisee/apbf/pipelines
