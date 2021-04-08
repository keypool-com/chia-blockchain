from typing import Dict, List, Optional, Tuple

from blspy import G1Element

from chia.types.announcement import Announcement
from chia.types.blockchain_format.coin import Coin
from chia.types.blockchain_format.program import Program
from chia.types.blockchain_format.sized_bytes import bytes32
from chia.types.condition_opcodes import ConditionOpcode
from chia.types.condition_var_pair import ConditionVarPair
from chia.util.clvm import int_from_bytes
from chia.util.errors import ConsensusError, Err
from chia.util.ints import uint64


def parse_sexp_to_condition(
    sexp: Program,
) -> Tuple[Optional[Err], Optional[ConditionVarPair]]:
    """
    Takes a ChiaLisp sexp and returns a ConditionVarPair.
    If it fails, returns an Error
    """
    if not sexp.listp():
        return Err.INVALID_CONDITION, None
    items = sexp.as_python()
    if not isinstance(items[0], bytes):
        return Err.INVALID_CONDITION, None
    try:
        opcode = ConditionOpcode(items[0])
    except ValueError:
        opcode = ConditionOpcode.UNKNOWN
    if len(items) == 3:
        return None, ConditionVarPair(opcode, [items[1], items[2]])
    return None, ConditionVarPair(opcode, [items[1]])


def parse_sexp_to_conditions(
    sexp: Program,
) -> Tuple[Optional[Err], Optional[List[ConditionVarPair]]]:
    """
    Takes a ChiaLisp sexp (list) and returns the list of ConditionVarPairs
    If it fails, returns as Error
    """
    results: List[ConditionVarPair] = []
    try:
        for _ in sexp.as_iter():
            error, cvp = parse_sexp_to_condition(_)
            if error:
                return error, None
            results.append(cvp)  # type: ignore # noqa
    except ConsensusError:
        return Err.INVALID_CONDITION, None
    return None, results


def conditions_by_opcode(
    conditions: List[ConditionVarPair],
) -> Dict[ConditionOpcode, List[ConditionVarPair]]:
    """
    Takes a list of ConditionVarPairs(CVP) and return dictionary of CVPs keyed of their opcode
    """
    d: Dict[ConditionOpcode, List[ConditionVarPair]] = {}
    cvp: ConditionVarPair
    for cvp in conditions:
        if cvp.opcode not in d:
            d[cvp.opcode] = list()
        d[cvp.opcode].append(cvp)
    return d


def pkm_pairs_for_conditions_dict(
    conditions_dict: Dict[ConditionOpcode, List[ConditionVarPair]],
    coin_name: bytes32 = None,
) -> List[Tuple[G1Element, bytes]]:
    ret: List[Tuple[G1Element, bytes]] = []
    for cvp in conditions_dict.get(ConditionOpcode.AGG_SIG, []):
        # TODO: check types
        # assert len(_) == 3
        assert cvp.vars[1] is not None
        ret.append((G1Element.from_bytes(cvp.vars[0]), cvp.vars[1]))
    if coin_name is not None:
        for cvp in conditions_dict.get(ConditionOpcode.AGG_SIG_ME, []):
            ret.append((G1Element.from_bytes(cvp.vars[0]), cvp.vars[1] + coin_name))
    return ret


def aggsig_in_conditions_dict(conditions_dict: Dict[ConditionOpcode, List[ConditionVarPair]]) -> List[ConditionVarPair]:
    agg_sig_conditions = []
    for _ in conditions_dict.get(ConditionOpcode.AGG_SIG, []):
        agg_sig_conditions.append(_)
    return agg_sig_conditions


def created_outputs_for_conditions_dict(
    conditions_dict: Dict[ConditionOpcode, List[ConditionVarPair]],
    input_coin_name: bytes32,
) -> List[Coin]:
    output_coins = []
    for cvp in conditions_dict.get(ConditionOpcode.CREATE_COIN, []):
        # TODO: check condition very carefully
        # (ensure there are the correct number and type of parameters)
        # maybe write a type-checking framework for conditions
        # and don't just fail with asserts
        puzzle_hash, amount_bin = cvp.vars[0], cvp.vars[1]
        amount = int_from_bytes(amount_bin)
        coin = Coin(input_coin_name, puzzle_hash, amount)
        output_coins.append(coin)
    return output_coins


def coin_announcements_for_conditions_dict(
    conditions_dict: Dict[ConditionOpcode, List[ConditionVarPair]],
    input_coin: Coin,
) -> List[Announcement]:
    output_announcements = []
    for cvp in conditions_dict.get(ConditionOpcode.CREATE_ANNOUNCEMENT_WITH_ID, []):
        message = cvp.vars[0]
        announcement = Announcement(input_coin.name(), message)
        output_announcements.append(announcement)
    return output_announcements


def puzzle_announcements_for_conditions_dict(
    conditions_dict: Dict[ConditionOpcode, List[ConditionVarPair]],
    input_coin: Coin,
) -> List[Announcement]:
    output_announcements = []
    for cvp in conditions_dict.get(ConditionOpcode.CREATE_ANNOUNCEMENT_WITH_PUZZLEHASH, []):
        message = cvp.vars[0]
        announcement = Announcement(input_coin.puzzle_hash, message)
        output_announcements.append(announcement)
    return output_announcements


def coin_announcements_names_for_npc(npc_list) -> List[bytes32]:
    output_announcements = []
    for npc in npc_list:
        for condition, cvp_list in npc.conditions:
            if condition == ConditionOpcode.CREATE_ANNOUNCEMENT_WITH_ID:
                for cvp in cvp_list:
                    message = cvp.vars[0]
                    announcement = Announcement(npc.coin_name, message)
                    output_announcements.append(announcement.name())
    return output_announcements


def puzzle_announcements_names_for_npc(npc_list) -> List[bytes32]:
    output_announcements = []
    for npc in npc_list:
        for condition, cvp_list in npc.conditions:
            if condition == ConditionOpcode.CREATE_ANNOUNCEMENT_WITH_PUZZLEHASH:
                for cvp in cvp_list:
                    message = cvp.vars[0]
                    announcement = Announcement(npc.puzzle_hash, message)
                    output_announcements.append(announcement.name())
    return output_announcements


def coin_announcement_names_for_conditions_dict(
    conditions_dict: Dict[ConditionOpcode, List[ConditionVarPair]],
    input_coin: Coin,
) -> List[bytes32]:
    output = [an.name() for an in coin_announcements_for_conditions_dict(conditions_dict, input_coin)]
    return output


def puzzle_announcement_names_for_conditions_dict(
    conditions_dict: Dict[ConditionOpcode, List[ConditionVarPair]],
    input_coin: Coin,
) -> List[bytes32]:
    output = [an.name() for an in puzzle_announcements_for_conditions_dict(conditions_dict, input_coin)]
    return output


def conditions_dict_for_solution(
    puzzle_reveal: Program,
    solution: Program,
) -> Tuple[Optional[Err], Optional[Dict[ConditionOpcode, List[ConditionVarPair]]], uint64]:
    error, result, cost = conditions_for_solution(puzzle_reveal, solution)
    if error or result is None:
        return error, None, uint64(0)
    return None, conditions_by_opcode(result), cost


def conditions_for_solution(
    puzzle_reveal: Program,
    solution: Program,
) -> Tuple[Optional[Err], Optional[List[ConditionVarPair]], uint64]:
    # get the standard script for a puzzle hash and feed in the solution
    try:
        cost, r = puzzle_reveal.run_with_cost(solution)
        error, result = parse_sexp_to_conditions(r)
        return error, result, uint64(cost)
    except Program.EvalError:
        return Err.SEXP_ERROR, None, uint64(0)
