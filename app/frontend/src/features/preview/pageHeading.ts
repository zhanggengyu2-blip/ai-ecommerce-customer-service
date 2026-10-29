import type { InjectionKey } from 'vue';

export interface PageHeadingData { title: string; description: string }
export interface PageHeadingContext {
  update(owner: symbol, data: PageHeadingData): void;
  release(owner: symbol): void;
}

export const PageHeadingKey: InjectionKey<PageHeadingContext> = Symbol('page-heading');
