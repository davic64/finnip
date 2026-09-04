import { format } from 'date-fns'

const formatDate = (date: Date): string => format(date, 'dd/MM/yyyy');

export default formatDate;