from src.sim.calibration import get_calibrator


def test_calibration_monotonic():
    calibrator = get_calibrator()
    drift_neg, vol_neg, skew_neg, kurt_neg = calibrator.calibrate(-0.8)
    drift_pos, vol_pos, skew_pos, kurt_pos = calibrator.calibrate(0.8)

    assert drift_neg < 0 < drift_pos
    assert vol_pos >= vol_neg
    assert skew_neg < 0 < skew_pos
    assert kurt_neg >= 3.0 and kurt_pos >= 3.0
