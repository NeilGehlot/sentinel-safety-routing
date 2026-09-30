# Movement classifier evaluation

## Datasets

- UCI HAR: Skipped. UCI HAR Dataset.names says: 'Any commercial use is prohibited.' The UCI catalog page also displays CC BY 4.0. This module follows the dataset notice and does not train on it. The UCI page lists a 50 Hz sampling rate and published windows of 2.56 s (128 samples).
- WISDM: Used. UCI catalog license: Creative Commons Attribution 4.0 International (CC BY 4.0), which allows use with attribution. Weiss, G. (2019). WISDM Smartphone and Smartwatch Activity and Biometrics Dataset. UCI Machine Learning Repository. https://doi.org/10.24432/C5HK59. Phone accelerometer only, sampled at 20 Hz. Windows are 2.5 s (50 samples). No vehicle activity and no fall activity are in this dataset.
- MobiAct: Skipped. The Biomedical Informatics and eHealth Laboratory says MobiAct is available on request for non-commercial research and education only, after a database usage agreement is signed (https://bmi.hmu.gr/the-mobifall-and-mobiact-datasets-2/). No agreement is in place, so the files were not downloaded. Capture uses SENSOR_DELAY_FASTEST, which is not one published sampling rate.
- Watch and gyroscope streams were not used.
- There is no struggle class.

## Windows

- Lines read: 4804403. Skipped lines: 3466336.
- Kept windows: 26651. Each window is 2.5 s at 20 Hz.
- Mapped codes: A walking, B jogging as running, C stairs as walking, D sitting as stationary, E standing as stationary.
- Vehicle is not a WISDM activity, so the forest has no vehicle class.
- Training completed on the windows below.

## Split

- Subjects are sorted, and every subject whose index modulo 5 is 4 is held out.
- A subject is entirely in train or entirely in test. Windows are not shuffled.
- Held-out subjects: 10.
- Test windows: 5114.

## Model

- Random forest. Not a neural net.
- n_estimators 100, max_depth 16, min_samples_leaf 5, class_weight balanced, random_state 0.
- Features: mean, std, min, max on each axis and on magnitude, dominant frequency, jerk std.

## Metrics

- Macro F1: 0.976186.
- Fall recall was not computed. The test labels do not include fall.
- Confusion matrix:
| true \ predicted | running | stationary | walking |
| --- | --- | --- | --- |
| running | 951 | 1 | 14 |
| stationary | 1 | 2052 | 22 |
| walking | 62 | 5 | 2006 |
