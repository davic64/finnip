import { persist, state } from '../state/state.service.js';

const MAX_SIZE = 1000;

export function isDuplicate(updateId: number): boolean {
    if (state.seenUpdates.includes(updateId)) {
        return true;
    }

    state.seenUpdates.push(updateId);

    if (state.seenUpdates.length > MAX_SIZE) {
        state.seenUpdates.shift();
    }

    persist();

    return false;
}
