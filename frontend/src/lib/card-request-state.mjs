/** Card ownership takes precedence over a historical request. Unknown statuses fail closed. */
export function cardRequestState(cards, requests, year) {
  if (cards.some(card => card.annee === year)) return 'card';
  const request = requests.find(item => item.annee === year);
  if (!request) return 'absent';
  if (request.status === 'rejected') return 'rejected';
  if (request.status === 'payment_required') return 'payment';
  if (request.status === 'pending') return 'pending';
  return 'blocked';
}
