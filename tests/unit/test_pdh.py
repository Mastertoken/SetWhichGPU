from conftest import LUID_ARC, LUID_BASIC, LUID_NV

from gpucc.monitoring.pdh_parse import parse_adapter_memory, parse_engine, parse_process_memory
from gpucc.monitoring.sources.pdh import build_sample

MIB = 1 << 20


def eng(pid, luid, engine, idx=0):
    return f"pid_{pid}_luid_0x00000000_0x{luid:08X}_phys_0_eng_{idx}_engtype_{engine}"


def pmem(pid, luid):
    return f"pid_{pid}_luid_0x00000000_0x{luid:08X}_phys_0"


def amem(luid):
    return f"luid_0x00000000_0x{luid:08X}_phys_0"


def test_parsers():
    assert parse_engine(eng(1234, LUID_ARC, "3D")) == (1234, LUID_ARC, "3D")
    assert parse_engine(eng(5, LUID_NV, "VideoDecode", 3)) == (5, LUID_NV, "VideoDecode")
    assert parse_engine("garbage") is None
    assert parse_process_memory(pmem(42, LUID_NV)) == (42, LUID_NV)
    assert parse_process_memory(eng(42, LUID_NV, "3D")) is None
    assert parse_adapter_memory(amem(LUID_ARC)) == LUID_ARC
    assert parse_engine("pid_1_luid_0x00000001_0x00000002_phys_0_eng_0_engtype_3D") == (1, (1 << 32) | 2, "3D")


def test_build_sample_aggregation(discovery, keys):
    luid_to_key = {g.luid: g.key for g in discovery.gpus}
    engines = {
        eng(100, LUID_ARC, "3D", 0): 30.0,
        eng(200, LUID_ARC, "3D", 0): 15.0,
        eng(200, LUID_ARC, "Copy", 1): 4.0,
        eng(300, LUID_NV, "Compute_0", 2): 80.0,
        eng(300, LUID_NV, "3D", 0): 0.0,
        eng(1, LUID_BASIC, "3D", 0): 50.0,  # software adapter → ignored
    }
    pm = {pmem(100, LUID_ARC): 1440 * MIB, pmem(400, LUID_NV): 8 * MIB, pmem(1, LUID_BASIC): MIB}
    am = {amem(LUID_ARC): 4590 * MIB, amem(LUID_NV): 4 * MIB}
    s = build_sample(luid_to_key, engines, pm, am)

    arc, nv, amd = s.readings[keys["intel"]], s.readings[keys["nvidia"]], s.readings[keys["amd"]]
    assert arc.utilization_pct == 45.0  # max over engines (3D: 30+15)
    assert arc.engines == {"3D": 45.0, "Copy": 4.0}
    assert arc.vram_used_bytes == 4590 * MIB
    assert nv.utilization_pct == 80.0
    assert amd.utilization_pct == 0.0 and amd.vram_used_bytes is None

    procs = {(p.pid, p.key): p for p in s.processes}
    assert procs[(100, keys["intel"])].dedicated_bytes == 1440 * MIB
    assert procs[(200, keys["intel"])].engines == {"3D": 15.0, "Copy": 4.0}
    assert procs[(300, keys["nvidia"])].engines == {"Compute_0": 80.0}  # zero engines dropped
    assert procs[(400, keys["nvidia"])].engines == {}
    assert all(p.pid != 1 for p in s.processes)


def test_utilization_capped_at_100(discovery, keys):
    luid_to_key = {g.luid: g.key for g in discovery.gpus}
    engines = {eng(i, LUID_ARC, "3D"): 40.0 for i in range(5)}
    s = build_sample(luid_to_key, engines, {}, {})
    assert s.readings[keys["intel"]].utilization_pct == 100.0
