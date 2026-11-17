"""Root-only real Engine objects plus disclosed test-only fault adapters.

No native delayed-enumeration behavior or shared daemon outage is asserted.
No authority/configuration is written to receiver stdin. Production entrypoints,
recipes, images and the signed-off pure modules remain unchanged.
"""
import hashlib
import json
import os
import re
import secrets
import sys
import time
import types

RECEIVER_LABEL = 'org.openqms.d4.nonce'
CASES = ('lost_create_reply', 'ambiguous_nonce', 'scoped_engine_io')


class CreateFaultFailure(Exception):
    pass


def require(value, code):
    if not value:
        raise CreateFaultFailure(code)


def identity(value):
    return type(value) is str and re.fullmatch('[a-f0-9]{64}', value) is not None


def retain_registration(initial):
    # Every case intentionally starts with missing convergence or inaccessible
    # current Engine facts. Later resource cleanup must not erase that evidence.
    return True


def verify_owned(raw, cid, nonce, image_id):
    require(identity(cid) and identity(nonce), 'cleanup_identity_invalid')
    require(type(raw) is dict and raw.get('Id') == cid and raw.get('Image') == image_id,
            'cleanup_id_or_image_mismatch')
    require(raw.get('Config', {}).get('Labels') == {RECEIVER_LABEL: nonce}, 'cleanup_nonce_mismatch')


def register_candidate(objects, cid, nonce, image_id, persist):
    require(identity(cid) and identity(nonce), 'create_id_invalid')
    item = dict(id=cid, nonce=nonce, image_id=image_id, create_pending=False,
                never_started=False, removed_by_runtime=False)
    # A returned full ID is cleanup authority only after fresh verification,
    # but it must survive any first inspect or receipt-write failure.
    objects.append(item)
    persist()
    return item


def observe_candidate(objects, cid, nonce, image_id, engine, persist):
    item = register_candidate(objects, cid, nonce, image_id, persist)
    raw = engine.inspect(cid, time.monotonic_ns() + 1_000_000_000)
    verify_owned(raw, cid, nonce, image_id)
    item['never_started'] = raw['State']['Status'] == 'created' and raw['State']['Pid'] == 0
    persist()
    return item


def cleanup_candidate(item, engine, collector, bindings, absent):
    try:
        raw = engine.inspect(item['id'], time.monotonic_ns() + 1_000_000_000)
    except Exception as error:
        if item['removed_by_runtime'] and str(error) == 'engine_not_found':
            return
        raise
    verify_owned(raw, item['id'], item['nonce'], item['image_id'])
    binding = item.get('binding')
    fresh = False
    if raw['State']['Running']:
        if binding is None:
            # This is a new current recipe/process/daemon/netns proof, never
            # reconstruction of kernel authority from an old serialized path.
            binding = collector.bind(item['nonce'], item['id'], time.monotonic_ns() + 2_000_000_000)
            bindings.append(binding)
            item['binding'] = binding
            fresh = True
        binding.signal('SIGKILL', time.monotonic_ns() + 500_000_000)
        if not fresh and binding.tasks_remaining() != 0:
            binding.terminate(time.monotonic_ns() + 2_000_000_000)
    elif binding is None:
        require(collector.verify_created(item['nonce'], item['id'],
                    time.monotonic_ns() + 2_000_000_000), 'cleanup_created_recipe_unverified')
    else:
        # Even a stopped object must retain the full fixed recipe before rm.
        collector._verified_inspect(item['nonce'], item['id'], time.monotonic_ns() + 2_000_000_000)
    if binding is not None:
        until = time.monotonic_ns() + 2_000_000_000
        while time.monotonic_ns() < until:
            current = engine.inspect(item['id'], min(until, time.monotonic_ns() + 200_000_000))
            verify_owned(current, item['id'], item['nonce'], item['image_id'])
            if current['State']['Running'] is False and binding.tasks_remaining() == 0:
                break
            time.sleep(.01)
        else:
            raise CreateFaultFailure('cleanup_receiver_not_stopped')
    engine.remove(item['id'], time.monotonic_ns() + 2_000_000_000)
    absent(item['id'])


class VisibilityEngine:
    """Explicit observer overlay, not a statement about Docker consistency."""
    def __init__(self, engine, nonce, hidden_rounds, records):
        require(identity(nonce) and type(hidden_rounds) is int and 1 <= hidden_rounds <= 3,
                'visibility_scope_invalid')
        self.engine, self.nonce = engine, nonce
        self.hidden_rounds, self.records, self.calls = hidden_rounds, records, 0

    def list_by_nonce(self, nonce, deadline_ns):
        require(nonce == self.nonce, 'visibility_nonce_outside_scope')
        actual = self.engine.list_by_nonce(nonce, deadline_ns)
        self.calls += 1
        returned = () if self.calls <= self.hidden_rounds else actual
        self.records.append(dict(round=self.calls, underlying_count=len(actual), returned_count=len(returned)))
        return returned

    def __getattr__(self, name):
        # A trusted test adapter delegates unchanged inspect/creation methods;
        # its sole deliberate behavioral change is the explicit list overlay.
        return getattr(self.engine, name)


class ScopedUnavailable:
    """Only this caller's management session fails; the daemon is never touched."""
    def __init__(self, nonce, engine_error):
        self.nonce, self.engine_error, self.calls = nonce, engine_error, 0

    def list_by_nonce(self, nonce, deadline_ns):
        require(nonce == self.nonce, 'engine_fault_nonce_outside_scope')
        self.calls += 1
        raise self.engine_error('engine_unavailable')


def helpers():
    fault = types.ModuleType('_owned_create_fault_helpers')
    fault.__dict__.update(PACKAGE_B64=PACKAGE_B64, PACKAGE_SHA256=PACKAGE_SHA256,
        WIRE_FIXTURE_SOURCE=WIRE_FIXTURE_SOURCE, WIRING_PROBE_SOURCE=WIRING_PROBE_SOURCE)
    exec(compile(FAULT_PROBE_SOURCE, '<owned-create-fault-helpers>', 'exec'), fault.__dict__)
    wiring = fault.helpers()
    fault.H, fault.UNITS = wiring, wiring.UNITS
    return wiring, fault


def prove_blocked(journal, nonce, store):
    from agent_d4_isolation.journal import SessionBlocked
    require(not journal.admission().may_open_session, 'unknown_allowed_new_session')
    journal_allowed = journal.delivery_gate(nonce).allowed
    invalidated = store.read(nonce)['invalidated']
    require(not journal_allowed or invalidated, 'unknown_allowed_delivery')
    try:
        journal.record_intent(secrets.token_hex(32))
    except SessionBlocked:
        return dict(journal_delivery_gate_allowed=journal_allowed, registration_invalidated=invalidated)
    raise CreateFaultFailure('unknown_allowed_new_intent')


def process_fact(engine, cid):
    raw = engine.inspect(cid, time.monotonic_ns() + 1_000_000_000)
    return {'id': raw['Id'], 'running': raw['State']['Running'], 'pid': raw['State']['Pid'],
            'started_at': raw['State']['StartedAt']}


def main(image_tag):
    require(os.geteuid() == 0 and CREATE_CASE in CASES, 'root_or_case_invalid')
    require(type(image_tag) is str and image_tag and not image_tag.startswith('-'), 'image_invalid')
    H, F = helpers()
    receipt = dict(case=CREATE_CASE, nonce=H.NONCE, root=str(H.ROOT), units=list(H.UNITS),
        bundle_sha256=PACKAGE_SHA256, create_probe_sha256=CREATE_PROBE_SHA256,
        wiring_probe_sha256=hashlib.sha256(WIRING_PROBE_SOURCE.encode()).hexdigest(),
        fault_helper_sha256=hashlib.sha256(FAULT_PROBE_SOURCE.encode()).hexdigest(),
        verified=False, resources_cleaned=False, registration_retained=True, bad_initial_record_retained=False,
        api_create_pending=False, failure_code=None, registry=[], secret_bytes_written=0,
        new_intent_blocked=False, delivery_blocked=False)
    engine = collector = lease = None
    objects, channels, bindings = [], [], []
    journal = store = None
    image_id = api_id = None

    def own(cid, nonce):
        return observe_candidate(objects, cid, nonce, image_id, engine, persist)

    def allocate(nonce):
        attempt = {'nonce': nonce, 'create_pending': True}
        receipt.setdefault('create_attempts', []).append(attempt); persist()
        cid = engine.create(nonce, image_id, api_id, time.monotonic_ns() + 3_000_000_000)
        attempt.update(id=cid, create_pending=False)
        return own(cid, nonce)

    def live(nonce):
        item = allocate(nonce)
        channel = engine.attach(item['id'], time.monotonic_ns() + 2_000_000_000)
        channels.append(channel)
        # Keep the attach channel open without ever calling write/close_stdin.
        engine.start(item['id'], time.monotonic_ns() + 2_000_000_000)
        item['never_started'] = False
        binding = collector.bind(nonce, item['id'], time.monotonic_ns() + 2_000_000_000)
        bindings.append(binding)
        item['binding'] = binding  # Removed from the serialized ledger below.
        return item, binding

    def serializable_receipt():
        return {**receipt, 'registry': [{key: value for key, value in item.items() if key != 'binding'}
                                       for item in objects]}

    # record_receipt serializes the public registry only, never live handles.
    def persist():
        H.record_receipt(serializable_receipt())

    def initial_bad():
        raw = H.safe_read(H.ROOT / 'state/journal' / (H.NONCE + '.json'))
        require(raw and raw['state'] != 'closed', 'initial_registration_not_bad')
        H.private_json(H.ROOT / 'bad-registration-initial.json', raw)
        H.private_json(H.ROOT / 'bad-session-initial.json', store.read(H.NONCE))
        receipt['initial_journal_summary'] = {key: raw.get(key) for key in
            ('state', 'doubted', 'revision', 'container_id', 'closed_by')}
        receipt['bad_initial_record_retained'] = True
        persist()

    try:
        H.unpack_package(); persist()
        image_id, api_id, manifest = F.setup_api(image_tag, receipt)
        sys.path.insert(0, str(H.ROOT))
        from agent_d4_isolation.linux_engine import EngineClient, EngineTransport, EngineError
        from agent_d4_isolation.linux_identity import KernelCollector
        from agent_d4_isolation.runtime_state import StateStore
        from agent_d4_isolation.runtime_supervisor import stop_session
        from agent_d4_isolation.runtime_network import prepare_api
        from agent_d4_isolation.journal import IntentJournal, CREATE_INFLIGHT
        from agent_d4_isolation.docker_api import DockerApi
        engine = EngineClient(); collector = KernelCollector(engine, image_id, api_id)
        lease = prepare_api(engine, manifest, time.monotonic_ns() + 5_000_000_000, install=True)
        (H.ROOT / 'state').mkdir(mode=0o700); (H.ROOT / 'state/journal').mkdir(mode=0o700)
        store = StateStore(H.ROOT); store.create(H.NONCE)
        journal = IntentJournal(store.journal_path)
        entry = journal.record_intent(H.NONCE)
        api_before = process_fact(engine, api_id)
        require(api_before['running'], 'api_not_live')

        if CREATE_CASE == 'lost_create_reply':
            receipt.update(timing_model='test_only_visibility_overlay_after_real_create', visibility=[],
                scope='direct_create_adapter_not_native_daemon_delay_or_controller_crash')
            class LostReplyTransport(EngineTransport):
                def exchange(self, payload, *, deadline_ns, limit):
                    request = json.loads(payload)
                    require(request['op'] == 'create', 'unexpected_controller_operation')
                    attempt = {'nonce': H.NONCE, 'create_pending': True}
                    receipt.setdefault('create_attempts', []).append(attempt); persist()
                    raw = super().exchange(payload, deadline_ns=deadline_ns, limit=limit)
                    reply = json.loads(raw)
                    # The trusted test receives an actual creation completion;
                    # only the controller-facing adapter loses this response.
                    attempt.update(id=reply['container_id'], create_pending=False)
                    item = own(reply['container_id'], H.NONCE)
                    raise EngineError('engine_unavailable')
            api = DockerApi(LostReplyTransport(engine, image_id, api_id), image_id, journal=journal,
                clock=time.monotonic_ns, op_deadline_ns=3_000_000_000, response_limit=262144)
            outcome = api.create(H.NONCE, expected_revision=entry.revision)
            require(outcome.kind == 'ambiguous' and len(objects) == 1, 'create_reply_was_not_lost')
            target = objects[0]
            require(target['never_started'] and collector.verify_created(H.NONCE, target['id'],
                    time.monotonic_ns() + 2_000_000_000), 'late_target_not_exact_never_started')
            initial_bad()
            wrapped = VisibilityEngine(engine, H.NONCE, 3, receipt['visibility'])
            for _ in range(3):
                result = stop_session(H.ROOT, H.NONCE, store=store, journal=journal,
                    engine=wrapped, collector=collector)
                require(result == 'isolation_unknown', 'empty_enumeration_reported_converged')
                receipt.update(prove_blocked(journal, H.NONCE, store))
                require(journal.load(H.NONCE).state != 'closed', 'empty_enumeration_closed_intent')
                require(engine.inspect(target['id'], time.monotonic_ns() + 1_000_000_000)['State']['Status'] == 'created',
                        'hidden_target_was_modified')
                persist()
            result = stop_session(H.ROOT, H.NONCE, store=store, journal=journal,
                engine=wrapped, collector=collector)
            require(result == 'isolation_unknown' and journal.load(H.NONCE).state != 'closed',
                    'late_cleanup_fabricated_create_convergence')
            try:
                engine.inspect(target['id'], time.monotonic_ns() + 1_000_000_000)
            except EngineError as error:
                require(str(error) == 'engine_not_found', 'late_absence_unknown')
            else:
                raise CreateFaultFailure('late_never_started_not_removed')
            target['removed_by_runtime'] = True
            receipt.update(late_never_started_removed=True, create_converged=store.read(H.NONCE)['create_converged'],
                           infrastructure_result=result)

        elif CREATE_CASE == 'ambiguous_nonce':
            receipt['scope'] = 'real_owned_nonce_collision_direct_stop_adapter'
            journal.transition(H.NONCE, entry.revision, CREATE_INFLIGHT)
            first, first_binding = live(H.NONCE)
            second, second_binding = live(H.NONCE)
            bystander, bystander_binding = live(secrets.token_hex(32))
            matches = engine.list_by_nonce(H.NONCE, time.monotonic_ns() + 2_000_000_000)
            require(set(matches) == {first['id'], second['id']} and bystander['id'] not in matches,
                    'nonce_filter_not_exact')
            receipt['ambiguous_exact_matches'] = len(matches)
            before = [process_fact(engine, item['id']) for item in objects]
            initial_bad()
            result = stop_session(H.ROOT, H.NONCE, store=store, journal=journal,
                engine=engine, collector=collector)
            require(result == 'isolation_unknown', 'ambiguity_reported_terminated')
            after = [process_fact(engine, item['id']) for item in objects]
            require(before == after and all(row['running'] for row in after) and
                    all(binding.tasks_remaining() > 0 for binding in bindings), 'ambiguous_stop_touched_object')
            receipt.update(all_three_unchanged=True, bystander_id=bystander['id'], infrastructure_result=result)

        else:
            receipt['scope'] = 'direct_stop_adapter_session_io_not_whole_supervision_chain'
            journal.transition(H.NONCE, entry.revision, CREATE_INFLIGHT)
            target, original = live(H.NONCE)
            bystander, bystander_binding = live(secrets.token_hex(32))
            current = journal.load(H.NONCE)
            bound, _ = journal.observe(H.NONCE, current.revision, (target['id'],), trusted=True)
            state = store.read(H.NONCE)
            store.update(H.NONCE, state['revision'], receiver_id=target['id'], create_converged=True,
                         snapshot=original.snapshot())
            require(bound.state == 'bound' and original.tasks_remaining() > 0, 'original_fd_not_live')
            before = process_fact(engine, bystander['id'])
            failed = ScopedUnavailable(H.NONCE, EngineError)
            # The external observer retains a capability but the fresh stop caller
            # is not given it. JSON cannot recreate a kernel termination handle.
            result = stop_session(H.ROOT, H.NONCE, store=store, journal=journal,
                engine=failed, collector=collector, binding=None)
            require(result == 'isolation_unknown' and process_fact(engine, target['id'])['running']
                    and original.tasks_remaining() > 0, 'fresh_stop_guessed_kernel_authority')
            receipt.update(fresh_without_fd_unknown=True, fresh_target_survived=True)
            initial_bad()
            started = time.monotonic_ns()
            result = stop_session(H.ROOT, H.NONCE, store=store, journal=journal,
                engine=failed, collector=collector, binding=original)
            until = started + 5_000_000_000
            while time.monotonic_ns() < until:
                facts = engine.inspect(target['id'], min(until, time.monotonic_ns() + 100_000_000))
                if original.tasks_remaining() == 0 and facts['State']['Running'] is False:
                    break
                time.sleep(.01)
            elapsed = time.monotonic_ns() - started
            require(result == 'isolation_unknown' and elapsed <= 5_000_000_000,
                    'engine_loss_reported_false_reclamation')
            require(original.tasks_remaining() == 0 and process_fact(engine, target['id'])['running'] is False,
                    'retained_fd_did_not_kill_exact_cgroup')
            require(process_fact(engine, bystander['id']) == before and bystander_binding.tasks_remaining() > 0,
                    'retained_fd_affected_bystander')
            receipt.update(original_fd_kernel_empty=True, kernel_elapsed_ns=elapsed,
                           bystander_id=bystander['id'], infrastructure_result=result)

        receipt.update(prove_blocked(journal, H.NONCE, store))
        receipt.update(new_intent_blocked=True, delivery_blocked=True)
        require(process_fact(engine, api_id) == api_before, 'api_affected_by_create_fault')
        require(H.docker('logs', api_id).stdout.decode('ascii').splitlines() == ['ready'],
                'unexpected_stdin_or_business_request')
        receipt['api_survived'] = True
        H.summarize_runtime(receipt)
        require(receipt['journal_summary']['state'] != 'closed', 'bad_registration_erased')
        receipt['verified'] = True
    except Exception as error:
        receipt['failure_code'] = str(error) if type(error) is CreateFaultFailure else 'create_fault_probe_failed'
    finally:
        api_id = api_id or receipt.get('api_id')
        image_id = image_id or receipt.get('image_id')
        errors = []
        def attempt(code, call):
            try:
                return call()
            except Exception:
                errors.append(code)
                return None
        # No test-created unit is expected, but these two exact nonce names are
        # the entire permitted systemd cleanup scope. Never touch docker.service.
        attempt('owned_unit_stop_unknown', lambda:H.run(['/usr/bin/systemctl', 'stop', *H.UNITS], timeout=15, check=False))
        attempt('owned_unit_reset_unknown', lambda:H.run(['/usr/bin/systemctl', 'reset-failed', *H.UNITS], check=False))
        for item in reversed(objects):
            attempt('exact_receiver_cleanup_unknown',
                    lambda item=item: cleanup_candidate(item, engine, collector, bindings, H.absent))
        for channel in channels:
            attempt('attach_close_unknown', channel.close)
        for binding in bindings:
            attempt('binding_close_unknown', binding.close)
        if lease is not None:
            attempt('api_lease_close_unknown', lease.close)
        if api_id is not None:
            def remove_api():
                H.assert_owned(api_id, image_id, 'api')
                H.docker('rm', '-f', api_id); H.absent(api_id)
            attempt('exact_api_cleanup_unknown', remove_api)
        def fresh_no_objects():
            require(not receipt.get('api_create_pending') and
                    not any(item.get('create_pending') for item in receipt.get('create_attempts', [])),
                    'unknown_create_requires_retained_evidence')
            nonces = {H.NONCE} | {item['nonce'] for item in objects}
            remaining = []
            if engine is not None:
                for nonce in nonces:
                    remaining.extend(engine.list_by_nonce(nonce, time.monotonic_ns() + 1_000_000_000))
            receipt['remaining_exact_ids'] = remaining
            require(not remaining and not H.exact_matches(H.SMOKE_LABEL), 'owned_resources_remain')
            for unit in H.UNITS:
                require(F.manager_view(unit)['LoadState'] == 'not-found', 'owned_unit_remains')
        attempt('fresh_cleanup_unverified', fresh_no_objects)
        def retain_bad_record():
            require(H.ROOT.exists() and (H.ROOT / 'bad-registration-initial.json').is_file(), 'bad_initial_record_missing')
            H.summarize_runtime(receipt, 'post_cleanup_')
            require(receipt.get('post_cleanup_journal_summary', {}).get('state') != 'closed', 'cleanup_closed_bad_intent')
            require(retain_registration(receipt.get('initial_journal_summary')), 'bad_registration_removal_requested')
        attempt('bad_registration_retention_unverified', retain_bad_record)
        receipt.update(resources_cleaned=not errors, cleanup_errors=errors, registration_retained=True)
        if errors:
            receipt['failure_code'] = receipt['failure_code'] or 'create_fault_cleanup_failed'
        try:
            persist()
        except Exception:
            errors.append('receipt_write_unknown')
            receipt['resources_cleaned'] = False
            receipt['failure_code'] = receipt['failure_code'] or 'create_fault_cleanup_failed'
        print(json.dumps(serializable_receipt(), sort_keys=True), flush=True)
    require(receipt['verified'] and receipt['resources_cleaned'] and receipt['failure_code'] is None,
            'create_fault_not_verified')
    print('runtime_create_fault_verified:' + CREATE_CASE, flush=True)


if __name__ == '__main__':
    try:
        require(len(sys.argv) == 2, 'image_required')
        main(sys.argv[1])
    except Exception as error:
        code = str(error) if type(error) is CreateFaultFailure else 'create_fault_probe_failed'
        print('runtime_create_fault_failed:' + code, flush=True)
        raise SystemExit(1)
