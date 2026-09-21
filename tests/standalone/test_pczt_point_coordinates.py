"""Optional public coordinates preserve transaction binding and parser isolation."""

import pytest
from application_client.pczt import PcztGlobal, PcztOrchardBundle, pczt_transaction_bytes
from application_client.zcash_command_sender import CLA, Errors, InsType, ZcashCommandSender
from application_client.zcash_verify_sign import (
    PALLAS_BASE_MODULUS,
    _pallas_point_from_bytes,
    check_orchard_spendauth_signature_validity,
    nu5_signature_digests,
)
from ragger.error import ExceptionRAPDU
from ragger.navigator.navigation_scenario import NavigationScenarioData, UseCase

from .test_pczt import _ORCHARD_TO_ORCHARD_SNAPSHOTS, _mixed_real_and_dummy_orchard_bundle, _review_approve
from .test_pczt_ironwood import PCZT_V6_GLOBAL, _ironwood_bundle_with_external_recipient


def _bundle(pool):
    return _mixed_real_and_dummy_orchard_bundle() if pool == "orchard" else _ironwood_bundle_with_external_recipient()


def _coordinates(encoded):
    point = _pallas_point_from_bytes(encoded)
    assert point is not None
    return tuple(value.to_bytes(32, "little") for value in point)


def _request(bundle, pool):
    return dict(
        pczt_global=PcztGlobal() if pool == "orchard" else PCZT_V6_GLOBAL,
        transparent_inputs=[],
        transparent_outputs=[],
        **{f"{pool}_bundle": bundle},
    )


def _inject(backend, monkeypatch, bundle, pool, kinds=(False, True), mutate=None, first_only=False):
    """Insert the optional APDUs at real output-header boundaries."""
    exchange = backend.exchange
    client = ZcashCommandSender(backend)
    instruction = InsType.PCZT_ORCHARD_ACTION if pool == "orchard" else InsType.PCZT_IRONWOOD_ACTION
    sent = []
    action_index = 0

    def wrapped(*args, **kwargs):
        nonlocal action_index
        response = exchange(*args, **kwargs)
        if action_index < len(bundle.actions):
            action = bundle.actions[action_index]
            if kwargs.get("ins") == instruction and kwargs.get("data") == action.cmx + action.ephemeral_key:
                index = action_index
                action_index += 1
                if not first_only or index == 0:
                    if kinds == (False, True) and mutate is None:
                        client.pczt_output_points(
                            b"".join(_coordinates(action.ephemeral_key)),
                            b"".join(_coordinates(action.recipient[11:])),
                            ironwood=pool == "ironwood",
                        )
                        sent.extend([(index, False), (index, True)])
                        return response
                    for recipient in kinds:
                        encoded = action.recipient[11:] if recipient else action.ephemeral_key
                        x, y = _coordinates(encoded)
                        if mutate:
                            x, y = mutate(index, recipient, x, y)
                        client.pczt_point_coordinates(x, y, ironwood=pool == "ironwood", recipient=recipient)
                        sent.append((index, recipient))
        return response

    monkeypatch.setattr(backend, "exchange", wrapped)
    return sent


def _sign_and_verify(client, pool, bundle):
    sign = client.pczt_sign_orchard if pool == "orchard" else client.pczt_sign_ironwood
    digest = None
    if pool == "orchard":
        tx = pczt_transaction_bytes(PcztGlobal(), [], [], bundle)
        digest = nu5_signature_digests(tx, [])["final_digest"]
    for index, action in enumerate(bundle.actions):
        if action.spend_value:
            signature = sign(action_index=index).data
            assert len(signature) == 64
            if digest is not None:
                assert check_orchard_spendauth_signature_validity(action.rk, signature, digest)


@pytest.mark.parametrize("pool", ["orchard", "ironwood"])
@pytest.mark.parametrize("kinds", [(False,), (True,), (False, True), (True, False)])
def test_pczt_supplied_points_sign(backend, scenario_navigator, monkeypatch, pool, kinds):
    bundle = _bundle(pool)
    sent = _inject(backend, monkeypatch, bundle, pool, kinds)
    client = ZcashCommandSender(backend)
    with client.send_pczt(**_request(bundle, pool)):
        # Reuse the existing review snapshots for this exact send, including its change.
        name = _ORCHARD_TO_ORCHARD_SNAPSHOTS if pool == "orchard" else "test_pczt_ironwood_display_private_transfer_with_change"
        _review_approve(scenario_navigator, name)
    assert len(sent) == len(bundle.actions) * len(kinds)
    _sign_and_verify(client, pool, bundle)


def _start_action(client, pool):
    bundle = _bundle(pool)
    client._send_pczt_header(PcztGlobal() if pool == "orchard" else PCZT_V6_GLOBAL)
    client._send_pczt_transparent_inputs([])
    client._send_pczt_transparent_outputs_sync([])
    if pool == "ironwood":
        client._send_pczt_orchard_actions_sync(PcztOrchardBundle([], 0, 0, bytes(32)))
    packets = getattr(client, f"_build_pczt_{pool}_action_packets")(bundle)
    instruction = InsType.PCZT_ORCHARD_ACTION if pool == "orchard" else InsType.PCZT_IRONWOOD_ACTION
    for index, packet in enumerate(packets[:4]):
        client.backend.exchange(cla=CLA, ins=instruction, p1=client._pczt_chunk_p1(index, len(packets)), p2=0, data=packet)
    return bundle, packets, instruction


@pytest.mark.parametrize("pool", ["orchard", "ironwood"])
@pytest.mark.parametrize(
    "case",
    [
        "off_curve",
        "wrong_point",
        "wrong_sign",
        "zero",
        "x_modulus",
        "y_modulus",
        "short",
        "long",
        "duplicate",
        "wrong_pool",
        "bad_p1",
        "bad_p2",
        "late",
    ],
)
def test_pczt_supplied_points_reject_invalid(backend, pool, case):
    client = ZcashCommandSender(backend)
    bundle, packets, instruction = _start_action(client, pool)
    x, y = _coordinates(bundle.actions[0].ephemeral_key)
    p1, p2 = int(pool == "ironwood"), 0
    expected = Errors.SW_INVALID_TRANSACTION
    if case == "off_curve":
        y = ((int.from_bytes(y, "little") + 2) % PALLAS_BASE_MODULUS).to_bytes(32, "little")
    elif case == "wrong_point":
        x, y = _coordinates(bundle.actions[1].ephemeral_key)
    elif case == "wrong_sign":
        y = (PALLAS_BASE_MODULUS - int.from_bytes(y, "little")).to_bytes(32, "little")
    elif case == "zero":
        x = y = bytes(32)
    elif case == "x_modulus":
        x = PALLAS_BASE_MODULUS.to_bytes(32, "little")
    elif case == "y_modulus":
        y = PALLAS_BASE_MODULUS.to_bytes(32, "little")
    elif case == "duplicate":
        client.pczt_point_coordinates(x, y, ironwood=bool(p1))
    elif case == "wrong_pool":
        p1 ^= 1
        expected = Errors.SW_BAD_STATE
    elif case in ("bad_p1", "bad_p2"):
        p1, p2 = (2, p2) if case == "bad_p1" else (p1, 3)
        expected = Errors.SW_WRONG_P1P2
    elif case == "late":
        backend.exchange(cla=CLA, ins=instruction, p1=0x80, p2=0, data=packets[4])
        expected = Errors.SW_BAD_STATE
    data = x + y
    if case in ("short", "long"):
        data = data[:-1] if case == "short" else data + b"\0"
        expected = Errors.SW_APP_WRONG_APDU_LENGTH
    with pytest.raises(ExceptionRAPDU) as error:
        backend.exchange(cla=CLA, ins=InsType.PCZT_POINT_COORDINATES, p1=p1, p2=p2, data=data)
    assert error.value.status == expected and not error.value.data
    # Failure clears the transaction and cannot leave a signable digest behind.
    sign = client.pczt_sign_orchard if pool == "orchard" else client.pczt_sign_ironwood
    with pytest.raises(ExceptionRAPDU) as error:
        sign(action_index=0)
    assert error.value.status == Errors.SW_CONDITIONS_OF_USE_NOT_SATISFIED and not error.value.data


@pytest.mark.parametrize("pool", ["orchard", "ironwood"])
@pytest.mark.parametrize("index", [0, 1])
def test_pczt_supplied_recipient_must_match_even_when_unused(backend, monkeypatch, pool, index):
    bundle = _bundle(pool)

    def wrong_recipient(action_index, recipient, x, y):
        # A valid curve point belonging to another output. Index 1 takes the IVK
        # path, so its recipient helper is checked even without outgoing recovery.
        return _coordinates(bundle.actions[1 - index].recipient[11:]) if action_index == index else (x, y)

    _inject(backend, monkeypatch, bundle, pool, (True,), wrong_recipient)
    client = ZcashCommandSender(backend)
    with pytest.raises(ExceptionRAPDU) as error:
        with client.send_pczt(**_request(bundle, pool)):
            pytest.fail("Mismatched recipient reached review")
    assert error.value.status == Errors.SW_INVALID_TRANSACTION and not error.value.data


@pytest.mark.parametrize("pool", ["orchard", "ironwood"])
def test_pczt_supplied_points_do_not_leak_to_next_action_or_transaction(backend, scenario_navigator, monkeypatch, pool):
    bundle = _bundle(pool)
    sent = _inject(backend, monkeypatch, bundle, pool, first_only=True)
    client = ZcashCommandSender(backend)
    for _ in range(2):
        # First transaction: helpers only on the first action. Second: no helpers.
        with client.send_pczt(**_request(bundle, pool)):
            _review_approve(scenario_navigator, "point_lifetime", compare=False)
        _sign_and_verify(client, pool, bundle)
        backend.wait_for_home_screen(timeout=10)
    assert sent == [(0, False), (0, True)]


@pytest.mark.parametrize("pool", ["orchard", "ironwood"])
def test_pczt_supplied_points_review_rejection(backend, scenario_navigator, monkeypatch, pool):
    bundle = _bundle(pool)
    _inject(backend, monkeypatch, bundle, pool)
    client = ZcashCommandSender(backend)
    with pytest.raises(ExceptionRAPDU) as error:
        with client.send_pczt(**_request(bundle, pool)):
            scenario = NavigationScenarioData(scenario_navigator.device, backend, UseCase.TX_REVIEW, False)
            scenario_navigator.navigator.navigate_until_text(
                navigate_instruction=scenario.navigation,
                validation_instructions=scenario.validation,
                text=scenario.pattern,
                screen_change_after_last_instruction=False,
            )
    assert error.value.status == Errors.SW_DENY and not error.value.data
    backend.wait_for_home_screen(timeout=10)
    sign = client.pczt_sign_orchard if pool == "orchard" else client.pczt_sign_ironwood
    with pytest.raises(ExceptionRAPDU) as error:
        sign(action_index=0)
    assert error.value.status == Errors.SW_CONDITIONS_OF_USE_NOT_SATISFIED


@pytest.mark.parametrize("pool", ["orchard", "ironwood"])
def test_pczt_supplied_points_error_then_fresh_transaction(backend, scenario_navigator, pool):
    client = ZcashCommandSender(backend)
    bundle, _, _ = _start_action(client, pool)
    x, y = _coordinates(bundle.actions[0].ephemeral_key)
    client.pczt_point_coordinates(x, y, ironwood=pool == "ironwood")
    with pytest.raises(ExceptionRAPDU) as error:
        client.pczt_point_coordinates(bytes(32), bytes(32), ironwood=pool == "ironwood", recipient=True)
    assert error.value.status == Errors.SW_INVALID_TRANSACTION
    # No intervening signing command or device restart resets this state for us.
    with client.send_pczt(**_request(bundle, pool)):
        _review_approve(scenario_navigator, "point_failure_recovery", compare=False)
    _sign_and_verify(client, pool, bundle)


@pytest.mark.parametrize("pool", ["orchard", "ironwood"])
@pytest.mark.parametrize("field", ["cmx", "enc_ciphertext", "out_ciphertext", "value"])
def test_pczt_supplied_points_preserve_output_checks(backend, monkeypatch, pool, field):
    bundle = _bundle(pool)
    action = bundle.actions[0]
    if field == "value":
        action.value += 1
    else:
        original = getattr(action, field)
        setattr(action, field, bytes([original[0] ^ 1]) + original[1:])
    _inject(backend, monkeypatch, bundle, pool)
    with pytest.raises(ExceptionRAPDU) as error:
        with ZcashCommandSender(backend).send_pczt(**_request(bundle, pool)):
            pytest.fail("Tampered output reached review with supplied coordinates")
    assert error.value.status == Errors.SW_INVALID_TRANSACTION and not error.value.data


@pytest.mark.parametrize("pool", ["orchard", "ironwood"])
@pytest.mark.parametrize("case", ["short", "long", "duplicate", "bad_second"])
def test_pczt_supplied_point_batch_rejects(backend, scenario_navigator, pool, case):
    client = ZcashCommandSender(backend)
    bundle, _, _ = _start_action(client, pool)
    action = bundle.actions[0]
    x, y = _coordinates(action.ephemeral_key)
    data = x + y + b"".join(_coordinates(action.recipient[11:]))
    expected = Errors.SW_INVALID_TRANSACTION
    if case in ("short", "long"):
        data = data[:-1] if case == "short" else data + b"\0"
        expected = Errors.SW_APP_WRONG_APDU_LENGTH
    elif case == "duplicate":
        client.pczt_point_coordinates(x, y, ironwood=pool == "ironwood")
    else:
        data = data[:64] + bytes(64)
    with pytest.raises(ExceptionRAPDU) as error:
        backend.exchange(cla=CLA, ins=InsType.PCZT_POINT_COORDINATES, p1=int(pool == "ironwood"), p2=2, data=data)
    assert error.value.status == expected and not error.value.data
    if case == "bad_second":
        # A validated first point must not survive failure of the second point.
        with client.send_pczt(**_request(bundle, pool)):
            _review_approve(scenario_navigator, "partial_batch_recovery", compare=False)
        _sign_and_verify(client, pool, bundle)
