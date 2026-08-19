# detection_model.pkl lives here at runtime

Not checked in — it's a ~1.7MB binary artifact that
`anomaly_detector.py` bootstraps automatically the first time it runs (see
that file's module docstring) if this directory doesn't already contain
one. Run `python3 blue-team/countermeasures/anomaly_detector.py` (or
`make anomaly-model`) to (re)generate it explicitly, e.g. after changing
`n_features` or `contamination`, or once you have real baseline telemetry
to train it on instead of the synthetic bootstrap data.
