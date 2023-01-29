# Mobile Accessibility Repair System

This project contains several core modules for the Mobile Accessibility Repair System (MARS), a pipeline for automatically detecting and repairing accessibility failures within Android apps. Specifically, there are scripts to run an automated crawler for Android apps, detect accessibility failures (following the guidelines used for Google's accessibility scanner), and generate repairs for the detected failures.


## Setup

1. Set up a Python virtual environment (we recommend [miniconda](https://docs.conda.io/en/latest/miniconda.html)).

    ```
    conda create -n mars python=3.7
    conda activate mars
    ```

2. Install python packages from requirements.txt.

    ```
    pip install -r requirements.txt
    ```

3. Set PYTHONPATH environment variable so imports work.

    ```
    export PYTHONPATH=".:$PYTHONPATH"
    ```

4. Create a `config.ini` file by copying `config.ini.example`.

    ```
    cp config.ini.example config.ini
    ```

5. Replace any missing config variables.

## Crawling Android Apps
1. Add pkgnames for apps you want to crawl to `apps.txt`. If there are apps that you want to skip but also leave in `apps.txt` for future crawls, you can specify their pkgnames in `skip.txt`.

2. Start an adb server if one is not already running, and check that your connected devices are detected via `adb`.

    ```
    adb devices
    ```

3. Start an interactive CLI to control crawl of multiple Android devices simutaneously

    ```
    python scripts/run_crawl.py
    ```

4. Once you have successfully started the CLI, your apps specified in `apps.txt` should automatically be distributed to any devices that are connected and have the app installed. You should see a prompt that looks like, into which you can enter some commands:
    ```
    >
    ```
    The following are commands for that might be useful in managing the crawl, and troubleshooting issues. Note some commands require an argument since they act on a device, which can be a specific `device` (specified by device ID) or `all` (run the command on all connected devices).

    - `status` - Prints useful information about the current crawl.
        - Output format:
        ```
        [<pid>] <device ID> | <crawl status> | <# of apps remaining> | <current pkg name> | <current pkg version>
        ```
        - `<crawl status>` can be one of not started, running, or stopped
    - `start [all | <device>]` - Starts a crawl process for each specified device.
    - `stop [all | <device>]` - Stops the crawl process for each specified device. This command also saves a snapshot of the crawler state, so future crawls can start from this checkpoint instead of from scratch.
    - `skip <device>` - This command is a combination of `stop` and `start` for a single device. This is useful when a user can determine that the crawler is stuck or is no longer capturing useful screens, and wants to proceed to crawling the next app without waiting for the full timeout.
    - `exit` - Exits the crawling CLI and performs necessary cleanup.
    - `reboot [all | <device>]` - Restarts the device(s). This can be useful when the required accessibility button is removed during the crawl of an app, or when something weird has happened to a device. Note the CLI will pause for 60 seconds while the device is rebooting.
    - `mute [all | <device>]` - Mutes the device(s). This can be useful because some apps have audio permissions and can turn the volume to max, which can cause noise disturbance issues during crawling. __Warning__: This command opens a volume controls floating overlay on the right hand side of the screen, which can potentially obstruct screenshot captures. Use only when necessary if crawler is active.


5. You can follow the status of the crawl by watching the crawl logs.

    ```
    tail -f data/crawl.log
    ```

6. General notes
- Minimize interactions with the devices during crawl time, as actions such as moving the phone or touching the screen may negatively affect the captured screenshot and view hierarchy, and the final crawl graph.
- The current crawler only supports crawling in portrait mode, since it relies on an accessibility button that appears on the toolbar only when the phone is in portrait mode.


## Running an Accessibility Scan
MARS includes a scanning module for potential accessibility issues, which is heavily inspired by Google's [Accessibility Scanner](https://play.google.com/store/apps/details?id=com.google.android.apps.accessibility.auditor&hl=en_US). MARS currently supports the following subset of the [checks](https://github.com/google/Accessibility-Test-Framework-for-Android/tree/master/src/main/java/com/google/android/apps/common/testing/accessibility/framework/checks) included in the Accessibility Scanner:
- `GraphicalViewHasSpeakableText` - screen-reader-focusable graphical views should be labeled with a content description
- `EditableTextHasHintText` - Android elements `EditTexts` and editable `TextViews` should be labeled with hint text, and not include a content description
- `RedundantDesc` - speakable text should not contain redundant information about the view's type (e.g., checked or button)
- `UninformativeLabel` - any graphical view should have an informative label (e.g., the label should not contain something like "temporary", "content label", etc.)
- `DuplicateSpeakableText` - Two views should not have the same speakable text, as this may be confusing to users (e.g., list items should be labeled with their specific element or with an index)

Some other reference materials:
- [Google's developer guidelines for accessibility](https://material.io/design/usability/accessibility.html#implementing-accessibility)
- [Accessibility Scanner Results](https://support.google.com/accessibility/android/answer/6376559)
- [Code](https://github.com/google/Accessibility-Test-Framework-for-Android) for Google's Accessibility Scanner and utils implementations (in Java)

## Repairing Accessibility Warnings & Failures
MARS includes a repair module for repairing accessibility failures detected in the accessibility scan.

    python scripts/repair_failures.py --crawl_ver <crawl_ver>


## End-To-End -- From Crawl to Repair

This is an example sequence of scripts to run the end-to-end pipeline, starting with crawling an Android app, and ending with a set of generated repairs for accessibility failures. The `crawl_ver` argument used in each script is a name (which can be any string, such as "2020.04") given to the specific instance of the crawl to identify it in future analyses. This argument should be kept constant across all scripts in one end-to-end run.

1. Run the crawl.

    ```
    python scripts/run_crawl.py
    ```

2. Fetch the app metadata from the Google Play Store and the app APKs.

    ```
    python scripts/fetch_metadata.py --crawl_ver <crawl_ver>
    ```

3. Run a number of post-processing steps on the crawled data, such as cleaning up orphaned files, broken screenshots, etc. This script also removes captured screens that are exactly identical in structure, which reduces the overall size of the crawled data by ~50%.

    ```
    python scripts/clean_crawl.py --crawl_ver <crawl_ver>
    ```

4. Group screens into "app states".

    ```
    python scripts/make_states.py --crawl_ver <crawl_ver> --method <xiaoyi|rico|mars>
    ```

    There are a number of methods to choose from to do this grouping:
    - `xiaoyi` - reimplements the base heuristics (without any expert hand-generated heuristics) from [this 2018 UIST paper](https://dl.acm.org/doi/10.1145/3242587.3242616)
    - `rico` - reimplements the heuristics from [this 2017 UIST paper](https://dl.acm.org/doi/10.1145/3126594.3126651)
    - `mars` - an extension of `xiaoyi` heuristics that considers additional heuristics such as restricting the set of resource ids to those containing ``android" or the package name

5. Run an accessibility scan with desired checks.

    ```
    python scripts/run_accessibility_scan.py --crawl_ver <crawl_ver>
    ```

6. Repair the detected failures.

    ```
    python scripts/repair_failures.py --crawl_ver <crawl_ver>
    ```

## Accessing the Database
All historical data from previous crawls are stored in a Postgres database, which can be accessed from any machine on the local network. The following are a list of tables and their descriptions:
- _apps_ - Contains all crawled apps and their metadata
- _views_ - Contains UUIDs for all screens. This corresponds to the filename of the captured view hierarchy (.json) and the screenshot (.png).
- _removed_views_ - Contains a log of UUIDs corresponding to screens that were removed during the post-processing phase after crawling.
- _failures_ - Contains scan results for all elements that were eligible for an accessibility check (including those that did not trigger an accessibility failure/warning)
- _labels_ - Contains labels generated for failures in `failures`. These could be automatically generated via computer vision, populated from some external crowdsourced labeling task, or expert-generated.
- _repairs_ - Contains final repaired labels for some failures in `failures`. Some elements could either not be repaired, or the repaired label was not deemed high quality enough to be considered "final".

The exact schema of these tables can be found in `db/schema.sql`.
