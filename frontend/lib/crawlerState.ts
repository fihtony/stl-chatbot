/**
 * Crawler state management
 * Manages the state of the web crawler process
 */

import { ChildProcess } from 'child_process';

interface CrawlerState {
  isRunning: boolean;
  startTime?: number;
  pagesProcessed?: number;
  pagesCrawled?: number;
  filesDownloaded?: number;
  linksFound?: number;
  errors?: number;
  error?: string;
}

// In-memory state (in production, use a database)
let crawlerState: CrawlerState = {
  isRunning: false,
};

let crawlerProcess: ChildProcess | null = null;

/**
 * Get current crawler state
 */
export function getCrawlerState(): CrawlerState {
  return { ...crawlerState };
}

/**
 * Set crawler state
 */
export function setCrawlerState(state: Partial<CrawlerState>): void {
  crawlerState = {
    ...crawlerState,
    ...state,
  };
}

/**
 * Get crawler process
 */
export function getCrawlerProcess(): ChildProcess | null {
  return crawlerProcess;
}

/**
 * Set crawler process
 */
export function setCrawlerProcess(process: ChildProcess | null): void {
  crawlerProcess = process;
}

/**
 * Reset crawler state to initial state
 */
export function resetCrawlerState(): void {
  crawlerState = {
    isRunning: false,
  };
  crawlerProcess = null;
}
