## A Large-Scale Longitudinal Analysis of Missing Label Accessibility Failures in Android Apps
Raymond Fok, Mingyuan Zhong, Anne Spencer Ross, James Fogarty, Jacob O. Wobbrock

We present the frst large-scale longitudinal analysis of missing label accessibility failures in Android apps. We developed a crawler and collected monthly snapshots of 312 apps over 16 months. We use this unique dataset in empirical examinations of accessibility not possible in prior datasets. Key large-scale fndings include missing label failures in 55.6% of unique image-based elements, longitudinal improvement in ImageButton elements but not in more prevalent ImageView elements, that 8.8% of unique screens are unreachable without navigating at least one missing label failure, that app failure rate does not improve with number of downloads, and that efective labeling is neither limited to nor guaranteed by large software organizations. We then examine longitudinal data in individual apps, presenting illustrative examples of accessibility impacts of systematic improvements, incomplete improvements, interface redesigns, and accessibility regressions. We discuss these fndings and potential opportunities for tools and practices to improve label-based accessibility.

### Code
Code for the original crawler used to collect app screens and associated accessibility metadata is found in `mars/`. The objective is to provide a semi-automatic crawling process of Android applications on physical devices, with some CLI controls for oversight. Please note that the code is not actively maintained, and YMMV.

### Data
The full dataset is large, containing many images and view hierarchies. A small smaple of longitudinal accessibility data is provided in `data/`.  Please contact the first author directly to request access to particular slices or the entirety of the dataset. See `apps.pdf` to see a list of all apps included in our analysis and for which we may have longitudinal data.

### Citation
If you use our work, please cite our paper

```
@inproceedings{fok_longa11y_2022,
    author = {Fok, Raymond and Zhong, Mingyuan and Ross, Anne Spencer and Fogarty, James and Wobbrock, Jacob O.},
    title = {A Large-Scale Longitudinal Analysis of Missing Label Accessibility Failures in Android Apps},
    year = {2022},
    isbn = {9781450391573},
    publisher = {Association for Computing Machinery},
    address = {New York, NY, USA},
    url = {https://doi.org/10.1145/3491102.3502143},
    articleno = {461},
    numpages = {16},
    location = {New Orleans, LA, USA},
    series = {CHI '22}
}
```
