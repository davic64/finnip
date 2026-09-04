const MAX_SIZE = 1000;
const seenUpdates = new Set<number>();

export function isDuplicate(updateId: number): boolean {
    if (seenUpdates.has(updateId)) {
        return true;
    }

    seenUpdates.add(updateId);

    if (seenUpdates.size > MAX_SIZE) {
        const iterator = seenUpdates.values();
        const oldestUpdateId = iterator.next().value;
        if (oldestUpdateId !== undefined) {
            seenUpdates.delete(oldestUpdateId);
        }
    }

    return false;
}