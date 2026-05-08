/**
 * Tests for the SearchableSelect primitive used by the audit log filters.
 *
 * Render the component standalone with controlled value/onChange — keeps the
 * tests reading like real interactions and avoids leaking into the panel's
 * concerns.
 */
import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { SearchableSelect } from '@/components/ui/searchable-select'

const OPTIONS = ['risk.create', 'risk.update', 'auth.login', 'user.deactivate']

function renderComponent(extraProps: Partial<React.ComponentProps<typeof SearchableSelect>> = {}) {
  const onChange = vi.fn()
  const utils = render(
    <SearchableSelect
      value=""
      onChange={onChange}
      options={OPTIONS}
      placeholder="(any)"
      {...extraProps}
    />,
  )
  return { onChange, ...utils }
}

/**
 * Render with internal state so we can observe the result of clearing/picking
 * via the rendered trigger label rather than digging into the component.
 */
function ControlledHarness({ initial = '', onChangeSpy }: { initial?: string; onChangeSpy?: (v: string) => void }) {
  const [value, setValue] = useState(initial)
  return (
    <SearchableSelect
      value={value}
      onChange={(v) => {
        setValue(v)
        onChangeSpy?.(v)
      }}
      options={OPTIONS}
      placeholder="(any)"
    />
  )
}

describe('SearchableSelect', () => {
  it('closed by default; clicking the trigger opens the popover and focuses the search input', async () => {
    const user = userEvent.setup()
    renderComponent()

    expect(screen.queryByPlaceholderText('Search...')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button'))

    const search = await screen.findByPlaceholderText('Search...')
    expect(search).toBeInTheDocument()
    // requestAnimationFrame schedules focus, so wait for it.
    await waitFor(() => expect(search).toHaveFocus())
  })

  it('typing in the search input filters the visible options case-insensitively', async () => {
    const user = userEvent.setup()
    renderComponent()
    await user.click(screen.getByRole('button'))
    const search = await screen.findByPlaceholderText('Search...')

    await user.type(search, 'RISK')

    expect(screen.getByText('risk.create')).toBeInTheDocument()
    expect(screen.getByText('risk.update')).toBeInTheDocument()
    expect(screen.queryByText('auth.login')).not.toBeInTheDocument()
    expect(screen.queryByText('user.deactivate')).not.toBeInTheDocument()
  })

  it('clicking an option calls onChange with that value and closes the popover', async () => {
    const user = userEvent.setup()
    const onChangeSpy = vi.fn()
    render(<ControlledHarness onChangeSpy={onChangeSpy} />)

    await user.click(screen.getByRole('button'))
    await user.click(await screen.findByText('auth.login'))

    expect(onChangeSpy).toHaveBeenCalledWith('auth.login')
    expect(screen.queryByPlaceholderText('Search...')).not.toBeInTheDocument()
  })

  it('the (any) / clear row at the top calls onChange with empty string and closes', async () => {
    const user = userEvent.setup()
    const onChangeSpy = vi.fn()
    render(<ControlledHarness initial="risk.create" onChangeSpy={onChangeSpy} />)

    await user.click(screen.getByRole('button'))
    await user.click(await screen.findByText(/\(any\) — clear selection/))

    expect(onChangeSpy).toHaveBeenCalledWith('')
    expect(screen.queryByPlaceholderText('Search...')).not.toBeInTheDocument()
  })

  it('pressing Escape closes the popover', async () => {
    const user = userEvent.setup()
    renderComponent()
    await user.click(screen.getByRole('button'))
    expect(await screen.findByPlaceholderText('Search...')).toBeInTheDocument()

    await user.keyboard('{Escape}')

    await waitFor(() =>
      expect(screen.queryByPlaceholderText('Search...')).not.toBeInTheDocument(),
    )
  })

  it('clicking outside the component closes the popover', async () => {
    const user = userEvent.setup()
    render(
      <div>
        <SearchableSelect value="" onChange={() => {}} options={OPTIONS} />
        <button data-testid="outside">outside</button>
      </div>,
    )

    await user.click(screen.getAllByRole('button')[0])
    expect(await screen.findByPlaceholderText('Search...')).toBeInTheDocument()

    // The component listens on mousedown; userEvent.click fires mousedown, so it suffices.
    await user.click(screen.getByTestId('outside'))

    await waitFor(() =>
      expect(screen.queryByPlaceholderText('Search...')).not.toBeInTheDocument(),
    )
  })

  it('arrow keys move highlight; Enter selects', async () => {
    const user = userEvent.setup()
    const onChangeSpy = vi.fn()
    render(<ControlledHarness onChangeSpy={onChangeSpy} />)

    await user.click(screen.getByRole('button'))
    await screen.findByPlaceholderText('Search...')

    // highlight starts at 0 (the clear row); ArrowDown -> first real option.
    await user.keyboard('{ArrowDown}{Enter}')

    expect(onChangeSpy).toHaveBeenCalledWith('risk.create')
  })

  it('emptyText renders when search filters everything out', async () => {
    const user = userEvent.setup()
    renderComponent({ emptyText: 'No matching actions' })
    await user.click(screen.getByRole('button'))
    const search = await screen.findByPlaceholderText('Search...')

    await user.type(search, 'zzznotreal')

    expect(screen.getByText('No matching actions')).toBeInTheDocument()
  })
})
