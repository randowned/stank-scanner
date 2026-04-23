import { writable, type Writable } from 'svelte/store';
import type { ConnectionStatus } from '$lib/types';

export const connectionStatus: Writable<ConnectionStatus> = writable('disconnected');
export const wsLatency: Writable<number> = writable(0);
