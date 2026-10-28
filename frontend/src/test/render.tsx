import type { ReactElement } from 'react'
import { MantineProvider } from '@mantine/core'
import { render as baseRender } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

export function render(ui: ReactElement, options: { route?: string } = {}) {
  return baseRender(
    <MantineProvider>
      <MemoryRouter initialEntries={[options.route ?? '/']}>{ui}</MemoryRouter>
    </MantineProvider>,
  )
}
