"""RF link budget calculation — ported verbatim from Madar's
`utils/rf_calc.py` (MISSIONS_REPORT.md §1.4/§1.9: "The calculators are pure
functions over ORM objects and port cleanly to another codebase"). No
behavior change; this file has no bugs of its own in the audit.
"""

import math
from dataclasses import dataclass


def free_space_path_loss_db(frequency_mhz: float, distance_km: float) -> float:
    """FSPL = 20*log10(d_m) + 20*log10(f_hz) - 147.55"""
    if frequency_mhz <= 0 or distance_km <= 0:
        return 0.0
    f_hz = frequency_mhz * 1e6
    d_m = distance_km * 1e3
    return 20 * math.log10(d_m) + 20 * math.log10(f_hz) - 147.55


def noise_power_dbm(data_rate_kbps: float, t_sys_k: float = 290.0) -> float:
    """Noise Power (dBm) = 10*log10(k * T_sys * BW) + 30; BW ~= data_rate (Hz)."""
    if data_rate_kbps <= 0:
        return 0.0
    k = 1.380649e-23  # Boltzmann constant, W/K/Hz
    bw = data_rate_kbps * 1e3  # Hz
    p_w = k * t_sys_k * bw
    return 10 * math.log10(p_w) + 30  # W -> dBm


@dataclass
class LinkCalcResult:
    assumed_distance_km: float
    transmit_power_dbm: float
    free_space_path_loss_db: float
    eirp_dbm: float
    received_power_dbm: float
    noise_power_dbm: float
    actual_signal_quality_db: float
    required_signal_quality_db: float
    system_link_margin_db: float
    link_status: str


def calculate_link_budget(
    downlink_frequency_mhz: float,
    satellite_antenna_gain_dbi: float,
    data_rate_kbps: float,
    required_signal_quality_db: float,
    transmit_power_dbm: float = 30.0,
    distance_km: float = 500.0,
    good_threshold_db: float = 3.0,
    weak_threshold_db: float = 0.0,
) -> LinkCalcResult:
    fspl = free_space_path_loss_db(downlink_frequency_mhz, distance_km)
    eirp = transmit_power_dbm + satellite_antenna_gain_dbi
    rx = eirp - fspl
    noise = noise_power_dbm(data_rate_kbps)
    actual_snr = rx - noise
    margin = actual_snr - required_signal_quality_db

    if margin > good_threshold_db:
        status = "Good Link"
    elif margin >= weak_threshold_db:
        status = "Weak Link"
    else:
        status = "Failed Link"

    return LinkCalcResult(
        assumed_distance_km=distance_km,
        transmit_power_dbm=transmit_power_dbm,
        free_space_path_loss_db=round(fspl, 4),
        eirp_dbm=round(eirp, 4),
        received_power_dbm=round(rx, 4),
        noise_power_dbm=round(noise, 4),
        actual_signal_quality_db=round(actual_snr, 4),
        required_signal_quality_db=required_signal_quality_db,
        system_link_margin_db=round(margin, 4),
        link_status=status,
    )


BAND_PRESETS = {
    "UHF": {
        "downlink_frequency_mhz": 437.5,
        "uplink_frequency_mhz": 145.8,
        "satellite_antenna_gain_dbi": 2.0,
        "data_rate_kbps": 9.6,
        "required_signal_quality_db": 9.6,
    },
    "S-Band": {
        "downlink_frequency_mhz": 2400.0,
        "uplink_frequency_mhz": 2025.0,
        "satellite_antenna_gain_dbi": 6.0,
        "data_rate_kbps": 100.0,
        "required_signal_quality_db": 12.0,
    },
}
